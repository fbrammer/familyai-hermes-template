"""
auto-context-manage module

Provides utilities for usage estimation, compaction decisions, carry-forward state building,
and idempotent journal entry creation before compaction.
"""

import re
import pathlib
from typing import List, Dict, Any

from ledger import EventKind, read_session
from auto_journal import should_journal, compose_entry, append_journal_entry

# Module-level cache for in-process deduplication during commit_before_compact.
# Keyed by event address (the [ADDRESS] field from the ledger).
_processed_event_ids: Dict[str, str] = {}


def estimate_usage_fraction(messages: List[Dict[str, Any]], model_window: int) -> float:
    if not messages:
        return 0.0

    total_chars = sum(len(m.get("content", "")) for m in messages)
    tokens = total_chars / 4.0
    return tokens / float(model_window)


def should_compact(
    usage_fraction: float,
    idle_seconds: float,
    has_open_blocking_op: bool,
    transition_confidence: float,
) -> str:
    if has_open_blocking_op:
        return "none"

    if transition_confidence >= 0.7 and usage_fraction >= 0.5:
        return "clear"

    if usage_fraction >= 0.88:
        return "hard_compact"

    if usage_fraction >= 0.75:
        return "compact"

    if idle_seconds > 1800 and usage_fraction >= 0.5:
        return "compact"

    if usage_fraction >= 0.6:
        return "soft"

    return "none"


def build_carry_forward(session_id: str, base_dir: str | None = None) -> Dict[str, Any]:
    session_events = read_session(session_id, base_dir=base_dir)

    active_project = None
    current_goal = None
    confirmed_decisions: List[Dict[str, Any]] = []
    touched_files: List[str] = []
    stated_constraints: List[str] = []

    seen_files: set = set()
    # op_id -> next_step for ops that have started but not (yet) ended, in
    # first-seen order. A single forward pass avoids order-dependency bugs a
    # reverse scan has: op_end always comes chronologically after its own
    # op_start, so op_end can only ever remove an id that's already present.
    open_op_next_steps: "dict[str, Any]" = {}

    for ev in session_events:
        kind = ev.get("kind")
        payload = ev.get("payload") or {}

        if ev.get("project") is not None:
            active_project = ev["project"]

        if "goal" in payload:
            current_goal = payload["goal"]

        if kind == "decision_confirmed":
            confirmed_decisions.append(payload if isinstance(payload, dict) else ev)

        if kind in ("file_created", "file_modified"):
            path = payload.get("path")
            if path and path not in seen_files:
                seen_files.add(path)
                touched_files.append(path)

        if kind == "op_start":
            op_id = ev.get("operation_id")
            if op_id:
                open_op_next_steps[op_id] = payload.get("next_step")

        if kind == "op_end":
            op_id = ev.get("operation_id")
            if op_id in open_op_next_steps:
                del open_op_next_steps[op_id]

        if kind == "constraint_stated":
            stated_constraints.append(payload.get("text"))

    open_operations = [
        {"operation_id": op_id, "next_step": next_step}
        for op_id, next_step in open_op_next_steps.items()
    ]

    return {
        "active_project": active_project,
        "current_goal": current_goal,
        "confirmed_decisions": confirmed_decisions,
        "touched_files": touched_files,
        "open_operations": open_operations,
        "stated_constraints": stated_constraints,
    }


def commit_before_compact(
    session_id: str,
    journal_dir: pathlib.Path,
    ledger_base_dir: str | None = None,
) -> None:
    session_events = read_session(session_id, base_dir=ledger_base_dir)

    for event in session_events:
        if not should_journal(event, session_events):
            continue

        event_id = event.get("event_id")
        later_committed = False
        for later in session_events:
            if later.get("kind") == "journal_committed":
                later_payload = later.get("payload") or {}
                if later_payload.get("event_id") == event_id:
                    later_committed = True
                    break
        if later_committed:
            continue

        address = event.get("address") or event_id
        if address is not None and address in _processed_event_ids:
            continue

        entry_md = compose_entry([event])
        # NOTE: compose_entry's real footer is
        # "<!-- id: <uuid> | project: ... | kind: ... | ops: ... -->", so the id is
        # NOT immediately followed by " -->" -- do not anchor the regex on that.
        match = re.search(r"<!-- id: ([a-f0-9\-]+)", entry_md)
        if not match:
            continue  # unexpected format; skip

        parsed_id = match.group(1)
        append_journal_entry(
            entry_md,
            {
                "id": parsed_id,
                "ts": event["ts"],
                "project": event.get("project"),
                "kind": event["kind"],
            },
            journal_dir,
        )

        _processed_event_ids[address] = parsed_id
