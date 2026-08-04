---
name: project-index
familyai_version: 0.1.0
description: >
  Silently tells apart "this belongs in an existing project" from "this is
  new" or "this is just a passing question," so a non-technical user never
  has to manually classify or route their own work.
requires:
  - session-ledger
---

# project-index

Maintains a lightweight, human-readable `project-index.md` (name, path,
purpose, keywords, last-updated, optional archived flag) and scores each
new request against it to decide whether work should route into an
existing project, land in a catch-all inbox, or stay untouched (a one-off
question, a draft that's still just conversation).

Tolerant of hand-editing: a malformed line is skipped and logged, not
fatal, and if more than half the file fails to parse in one pass the
whole file is treated as unreliable for that session rather than trusted
partially. Every operation that creates or moves files gets a small
manifest recording what happened, so a user's correction ("no, that's for
the other project") can move only what was actually created, without
touching files the user already owned or reversing anything external.
