import contextlib
import datetime
import enum
import json
import os
import pathlib
import threading
import time
from typing import Any, Dict, List, Optional, Union

from ulid import ULID


class EventKind(str, enum.Enum):
    DECISION_PROPOSED = "decision_proposed"
    DECISION_CONFIRMED = "decision_confirmed"
    DECISION_REVERSED = "decision_reversed"
    OP_START = "op_start"
    OP_END = "op_end"
    FILE_CREATED = "file_created"
    FILE_MODIFIED = "file_modified"
    EXTERNAL_ACTION = "external_action"
    CONSTRAINT_STATED = "constraint_stated"
    ROUTE_DECIDED = "route_decided"
    ROUTE_CORRECTED = "route_corrected"
    JOURNAL_COMMITTED = "journal_committed"


@contextlib.contextmanager
def with_file_lock(path: Union[str, pathlib.Path]):
    lock_path = str(path) + ".lock"
    start_time = time.time()
    timeout = 10.0
    fd = None

    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            break
        except OSError:
            try:
                age = time.time() - os.path.getmtime(lock_path)
                if age >= timeout:
                    # Holder likely died without releasing (e.g. SIGKILL).
                    # Break the stale lock rather than waiting forever.
                    os.unlink(lock_path)
                    continue
            except OSError:
                pass  # lock file vanished between the failed open and stat/unlink; retry
            if time.time() - start_time >= timeout:
                raise TimeoutError(f"Could not acquire lock for {path} within {timeout} seconds")
            time.sleep(0.01)

    try:
        yield
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            os.unlink(lock_path)
        except OSError:
            pass


_ulid_lock = threading.Lock()
_last_ulid_ms: Optional[int] = None
_last_ulid_int: Optional[int] = None


def _generate_ulid() -> str:
    """Monotonic within this process: python-ulid's ULID() has no built-in
    monotonicity, so two calls landing in the same millisecond can otherwise
    sort in random order. We track the last (ms, int-value) pair and, on a
    same-millisecond collision, increment the previous value by 1 rather than
    drawing fresh randomness. This guarantees lexical order matches creation
    order for this process; cross-process ordering still relies on the
    millisecond timestamp component, which is sufficient at this system's
    single-user, single-process-per-session scale."""
    global _last_ulid_ms, _last_ulid_int
    with _ulid_lock:
        u = ULID()
        ms = u.milliseconds
        value = int(u)
        if _last_ulid_ms == ms and _last_ulid_int is not None and value <= _last_ulid_int:
            value = _last_ulid_int + 1
            u = ULID.from_int(value)
        _last_ulid_ms = ms
        _last_ulid_int = value
        return str(u)


def append_event(
    session_id: str,
    kind: Union[EventKind, str],
    operation_id: Optional[str] = None,
    project: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    base_dir: Optional[pathlib.Path] = None,
) -> str:
    if isinstance(kind, EventKind):
        event_kind = kind
    elif isinstance(kind, str):
        try:
            event_kind = EventKind(kind)
        except ValueError:
            raise ValueError(f"Invalid EventKind: {kind}")
    else:
        raise ValueError(f"Invalid EventKind: {kind}")

    if base_dir is None:
        base_dir = pathlib.Path.home() / ".hermes" / "familyai"
    else:
        base_dir = pathlib.Path(base_dir)

    sessions_dir = base_dir / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    ledger_file = sessions_dir / f"{session_id}.ledger.json"

    event_id = _generate_ulid()
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if ts.endswith("+00:00"):
        ts = ts[:-6] + "Z"

    record = {
        "event_id": event_id,
        "ts": ts,
        "kind": event_kind.value,
        "operation_id": operation_id,
        "project": project,
        "payload": payload,
    }

    with with_file_lock(ledger_file):
        with open(ledger_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    return event_id


def read_session(
    session_id: str,
    base_dir: Optional[pathlib.Path] = None,
) -> List[Dict[str, Any]]:
    if base_dir is None:
        base_dir = pathlib.Path.home() / ".hermes" / "familyai"
    else:
        base_dir = pathlib.Path(base_dir)

    ledger_file = base_dir / "sessions" / f"{session_id}.ledger.json"

    if not ledger_file.is_file():
        return []

    records = []
    with open(ledger_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            if i == len(lines) - 1:
                # Unlocked reads can race a writer mid-append; a malformed
                # final line most likely means we read a partial flush.
                # Earlier lines are already durably written, so surface
                # everything else rather than failing the whole read.
                continue
            raise

    return records
