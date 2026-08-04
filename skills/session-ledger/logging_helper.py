import json
import os
import pathlib
from typing import Any, Optional

from ledger import with_file_lock

ALLOWED_FIELDS = frozenset({
    "component",
    "session_id",
    "level",
    "event_id",
    "operation_id",
    "project",
    "message",
})


def log_line(
    component: str,
    session_id: str,
    level: str,
    log_path: Optional[pathlib.Path] = None,
    **fields: Any,
) -> None:
    for key in fields:
        if key not in ALLOWED_FIELDS:
            raise ValueError(f"Disallowed log field: {key}")

    if log_path is None:
        log_path = pathlib.Path.home() / ".hermes" / "familyai" / "logs" / "familyai-skills.log"
    else:
        log_path = pathlib.Path(log_path)

    log_path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "component": component,
        "session_id": session_id,
        "level": level,
    }
    record.update(fields)

    with with_file_lock(log_path):
        if log_path.exists() and log_path.stat().st_size >= 5 * 1024 * 1024:
            rot2 = log_path.parent / (log_path.name + ".2")
            rot1 = log_path.parent / (log_path.name + ".1")

            if rot1.exists():
                os.replace(rot1, rot2)

            os.replace(log_path, rot1)

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
