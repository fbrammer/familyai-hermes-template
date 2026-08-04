---
name: auto-journal
familyai_version: 0.1.0
description: >
  Silently keeps a running journal of what was decided and done, so a
  non-technical user never has to remember to log anything themselves.
requires:
  - session-ledger
---

# auto-journal

Watches the session ledger for milestone-shaped events -- a decision the
user actually confirmed, a completed and verified piece of work, a
resolved routing decision -- and writes one journal entry per milestone to
`~/.hermes/familyai/journal/JOURNAL.md`, with a machine-readable footer in
an `index.jsonl` alongside it.

Entries are immutable: a later correction never edits or deletes a prior
entry, it adds a new entry that supersedes it (`relation:
incorrect|reversed|state-changed-since`). Sensitive topics (medical,
financial, legal, identity) are recorded at the topic level only, never
with the underlying detail.

A safety-net pass runs at session end so nothing that qualified gets
silently lost if the milestone-time write was missed. None of this is
visible to the user during normal use -- no chat notifications, no prompts
-- it just accumulates. The user can ask to see it, or turn it off,
any time.
