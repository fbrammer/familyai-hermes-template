---
name: session-ledger
familyai_version: 0.1.1
whats_new: Journal session state now uses the user-owned ~/AI/Journal/state/ location.
description: >
  Shared, append-only event ledger that the auto-journal,
  auto-context-manage, and project-index skills are built on. Not
  user-facing on its own -- installed alongside the other three so their
  imports resolve.
---

# session-ledger

This is shared runtime, not a skill you invoke directly. It provides:

- `ledger.py` -- the append-only per-session event log (`sessions/<id>.ledger.json`),
  a closed `EventKind` enum, and the single locking primitive every other
  skill reuses for its own writes.
- `logging_helper.py` -- allowlisted-field structured logging with
  size-based rotation, used by the other skills so nothing ever writes raw
  request text or file contents to a log file.
- `session_end.py` -- the transactional session-end sequence
  (`finalize_session`) and the one shared transition-confidence signal
  (`shared_transition_confidence`) that both auto-context-manage's
  topic-shift-clear decision and project-index's routing consult read, so
  the two skills can't disagree about whether a topic boundary just
  happened.

No configuration and no user-visible behavior of its own -- everything here
exists so the other three skills can compose safely.
