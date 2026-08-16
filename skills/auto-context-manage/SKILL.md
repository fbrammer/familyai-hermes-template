---
name: auto-context-manage
familyai_version: 0.1.0
description: >
  Silently manages context usage (soft/compact/hard-compact/clear) so a
  non-technical user never has to know when or how to compact or clear.
requires:
  - session-ledger
  - session-log
---

# auto-context-manage

Tracks an estimated usage fraction against the active model's context
window and decides, on a fixed threshold table, whether nothing needs to
happen yet (`none`), a light nudge is due (`soft`), a real compaction is
due (`compact`), an aggressive one is due (`hard_compact`), or the
conversation has clearly moved on to something unrelated and a full
`clear` is warranted.

Never compacts mid-operation (an open, blocking piece of work always wins
over a usage threshold). Before any compaction or clear, always commits
any not-yet-logged milestones through session-log first
(`commit_before_compact`) -- durability before context loss, never the
other way around. After compacting, rebuilds a carry-forward summary
(active project, current goal, confirmed decisions, touched files, open
operations with their next step, stated constraints) so the conversation
picks back up without the user noticing anything happened.
