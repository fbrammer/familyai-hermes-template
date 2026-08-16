---
name: session-log
familyai_version: 0.3.0
whats_new: >
  Renamed from auto-journal to session-log so the word "journal" belongs
  exclusively to the user-facing journal trigger. This skill's silent
  stream moved out of the human journal files (JOURNAL.md/entries/) into
  its own state files under ~/AI/Journal/state/session-log/.
description: >
  Silently keeps a running log of what was decided and done, so a
  non-technical user never has to remember to log anything themselves.
  There is also an occasional, skippable prompt inviting the user to add
  a note in their own words; it is entirely optional and the silent
  capture carries on regardless of whether the user engages with it or
  not.
requires:
  - session-ledger
---

# session-log

Watches the session ledger for milestone-shaped events -- a decision the
user actually confirmed, a completed and verified piece of work, a
resolved routing decision -- and writes one log entry per milestone to
`~/AI/Journal/state/session-log/SESSION-LOG.md`, with a machine-readable
footer recorded alongside it in `session-log.jsonl`.

This is a separate stream from the human-authored journal (triggered by
the word "journal", stored in `~/AI/Journal/JOURNAL.md` and `entries/`).
The two never share files or formats -- this skill never writes to
`JOURNAL.md`, `entries/`, or `index.jsonl`.

Entries are immutable: a later correction never edits or deletes a prior
entry, it adds a new entry that supersedes it (`relation:
incorrect|reversed|state-changed-since`). Sensitive topics (medical,
financial, legal, identity) are recorded at the topic level only, never
with the underlying detail.

The milestone capture itself is still fully silent and automatic -- it
produces no chat notifications of its own and requires nothing from the
user -- it just accumulates in the background. The one exception is the
reflection prompt described below, which is the only place this skill
ever asks the user anything; everything about the silent capture remains
exactly as invisible as before.

A safety-net pass runs at session end so nothing that qualified gets
silently lost if the milestone-time write was missed. The user can ask to
see the underlying session log, or turn it off, any time -- it is
separate from their journal.

## Reflection prompt (optional, skippable)

On top of the silent capture, there is a single occasional, optional
prompt that invites the user to add a note in their own words. It fires
only at an explicit session end -- not at the idle-timeout safety-net
sweep and not at the pre-compaction hook. Both of those still run for the
silent capture, but they are skipped for the reflection prompt because they
catch a user who has stepped away or is mid-context-juggling, not one at a
natural stopping point.

At explicit session end, call `should_prompt_reflection(session_events, journal_dir)`.
If it returns True, ask the user in chat:

"Want to add a note about this session in your own words?"

- If the user says no, or doesn't respond: call
  `handle_reflection_decline(journal_dir)` and move on. Do not ask again
  that session. Do not explain the backoff/cooldown mechanics to the user.

- If the user says yes: say something like "Go ahead, I'm listening," take
  their free-text reply verbatim, and call
  `handle_reflection_accept(journal_dir, text, project=<current project slug or None>)`.

- If the user's answer is ambiguous -- neither a clear yes nor a clear no
  (examples: "sure, what should I write?", "not now", "huh?") -- ask one
  clarifying yes/no question. If it's still ambiguous after that, treat it
  as a decline (call `handle_reflection_decline(journal_dir)`).

This is the one place session-log asks the user anything. Everything else
in the skill remains exactly as silent as before -- this is additive, not a
change to how milestones are silently captured.
