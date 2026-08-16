from pathlib import Path
import json
from datetime import datetime, timezone

from ledger import read_session
from auto_context_manage import commit_before_compact


def shared_transition_confidence(session_id: str, purpose: str, base_dir=None) -> float:
    """Calculate confidence of transition based on the last session event.

    Args:
        session_id: The ID of the session.
        purpose: Either 'compaction' or 'routing'. Must be one of these two strings.
        base_dir: Optional base directory for the ledger.

    Returns:
        float: 0.85 if the last event is a route_decided with topic_boundary=True,
        0.1 otherwise. Returns 0.0 if the session has no events.
    """
    if purpose not in ("compaction", "routing"):
        raise ValueError(f"Invalid purpose '{purpose}'. Must be 'compaction' or 'routing'.")

    events = read_session(session_id, base_dir=base_dir)
    if not events:
        return 0.0

    last_event = events[-1]
    if (
        last_event.get("kind") == "route_decided"
        and isinstance(last_event.get("payload"), dict)
        and last_event["payload"].get("topic_boundary") is True
    ):
        return 0.85

    return 0.1


def finalize_session(session_id: str, journal_dir: Path, ledger_base_dir=None) -> dict:
    """Finalize a session by committing its journal and creating a marker file.

    This function performs a transactional outbox sequence for ending a session.

    Args:
        session_id: The ID of the session to finalize.
        journal_dir: The directory containing the journal entries for the session.
        ledger_base_dir: Optional base directory for the ledger.

    Returns:
        dict: A status dictionary indicating whether the session was finalized or
        was already finalized.

    Raises:
        Exception: Any exception raised by `commit_before_compact` is propagated.
    """
    marker_dir = (
        Path(ledger_base_dir) if ledger_base_dir else Path.home() / "AI" / "Journal" / "state"
    )
    marker_path = marker_dir / "sessions" / f"{session_id}.finalized"

    if marker_path.exists():
        return {"status": "already_finalized", "journal_committed": False}

    try:
        commit_before_compact(session_id, journal_dir, ledger_base_dir)
    except Exception as e:
        raise e

    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(
        json.dumps({"finalized_at": datetime.now(timezone.utc).isoformat()})
    )

    return {"status": "finalized", "journal_committed": True}
