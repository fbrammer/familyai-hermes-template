"""Per-family-member escalation rate limiting, enforced locally on the
family member's own machine so a limit hit never makes a network call
and never spams Frank (see Phase 7 design spec, roundtable point on
source-side rate limiting)."""

import json
import pathlib
import time as _time

_DAY_SECONDS = 24 * 3600


def check_and_record(ledger_path: pathlib.Path, max_per_day: int = 3, now: float | None = None) -> dict:
    if now is None:
        now = _time.time()

    timestamps = _load(ledger_path)
    timestamps = [t for t in timestamps if now - t < _DAY_SECONDS]

    if len(timestamps) >= max_per_day:
        _save(ledger_path, timestamps)
        return {"allowed": False, "remaining": 0, "reset_at": min(timestamps) + _DAY_SECONDS}

    timestamps.append(now)
    _save(ledger_path, timestamps)
    remaining = max_per_day - len(timestamps)
    reset_at = (min(timestamps) + _DAY_SECONDS) if timestamps else now + _DAY_SECONDS
    return {"allowed": True, "remaining": remaining, "reset_at": reset_at}


def _load(ledger_path: pathlib.Path) -> list[float]:
    if not ledger_path.exists():
        return []
    try:
        data = json.loads(ledger_path.read_text())
        return list(data.get("timestamps", []))
    except Exception:
        return []


def _save(ledger_path: pathlib.Path, timestamps: list[float]) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps({"timestamps": timestamps}))
