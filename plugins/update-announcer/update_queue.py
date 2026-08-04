"""Standalone copy for the update-announcer Hermes plugin.

Deliberately self-contained (no import from ledger.py/logging_helper.py):
this file ships inside a Hermes *plugin*, which doesn't share a Python path
with scripts/skills/, and pulling in ledger.py would drag python-ulid into
a plugin that only ever needed one small file-locking helper. The canonical,
tested copy of this module lives at scripts/skills/update_queue.py -- keep
both in sync by hand when either changes (same convention already used for
every other skill file bundled under onboarding/hermes-template-config/).
"""
import contextlib
import datetime
import json
import os
import pathlib
import time
from datetime import timezone


@contextlib.contextmanager
def _with_file_lock(path):
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
                    os.unlink(lock_path)
                    continue
            except OSError:
                pass
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


def _log_line(message: str) -> None:
    # Best-effort diagnostic only -- never allowed to raise or block a read.
    try:
        print(f"[update-announcer] {message}")
    except Exception:
        pass


def append_pending_update(base_dir: pathlib.Path, skill: str, from_version: str, to_version: str, blurb: str) -> None:
    base_dir.mkdir(parents=True, exist_ok=True)
    file_path = base_dir / "pending-notable-updates.jsonl"

    now_utc = datetime.datetime.now(timezone.utc).isoformat()
    if now_utc.endswith("+00:00"):
        now_utc = now_utc[:-6] + "Z"

    entry = {
        "skill": skill,
        "from_version": from_version,
        "to_version": to_version,
        "blurb": blurb,
        "ts": now_utc,
    }

    line = json.dumps(entry) + "\n"
    with _with_file_lock(file_path):
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(line)


def read_pending(base_dir: pathlib.Path) -> list[dict]:
    file_path = base_dir / "pending-notable-updates.jsonl"
    if not file_path.exists():
        return []

    entries = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
                entries.append(data)
            except Exception:
                _log_line(f"skipping malformed pending-update line: {line!r}")
    return entries


def clear_pending(base_dir: pathlib.Path) -> None:
    file_path = base_dir / "pending-notable-updates.jsonl"

    with _with_file_lock(file_path):
        if not file_path.exists():
            return

        temp_path = base_dir / f"pending-notable-updates.tmp.{os.getpid()}"
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write("")

        os.replace(temp_path, file_path)


def compose_digest(entries: list[dict]) -> str:
    if not entries:
        raise ValueError("compose_digest called with no entries")

    if len(entries) == 1:
        return f"One thing got better since we last talked: {entries[0]['blurb']}"

    lines = ["A few things got better since we last talked:"]
    for entry in entries:
        lines.append(f"- {entry['blurb']}")
    return "\n".join(lines)


def load_prefs(base_dir: pathlib.Path) -> dict:
    file_path = base_dir / "update-announcements.json"
    default_prefs = {"enabled": True, "ever_delivered": False}

    if not file_path.exists():
        return default_prefs.copy()

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            loaded_data = json.load(f)
        if not isinstance(loaded_data, dict):
            return default_prefs.copy()
        return {**default_prefs, **loaded_data}
    except Exception:
        return default_prefs.copy()


def save_prefs(base_dir: pathlib.Path, prefs: dict) -> None:
    base_dir.mkdir(parents=True, exist_ok=True)
    file_path = base_dir / "update-announcements.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(prefs, f)
