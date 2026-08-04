---
name: update-announcer
familyai_version: 0.1.0
kind: plugin
description: >
  Tells the user, once per session, about any notable skill update they
  haven't heard about yet -- never interrupts their first message, never
  more than one combined digest per session, silent when there's nothing
  to say.
---

# update-announcer

**Not read by Hermes.** This file exists purely as this project's own
publish-pipeline metadata (version, what's-new blurb, and `kind: plugin`
so the refresher installs it to `plugins/` instead of `skills/`) — Hermes
itself only reads this directory's `plugin.yaml`.

Depends on `update_queue.py` (bundled alongside it in this same directory
-- plugins don't share a Python import path with `scripts/skills/`, so
this is a standalone copy, not an import from the session-ledger skills).
Does not depend on the session-ledger substrate at all, unlike every
Phase 2 skill.

What it does: on `on_session_start`, checks for a pending notable-update
digest and stashes it if there is one; on the first `post_llm_call` of
that same session (after the user's own message has already been
answered, agent now idle), delivers the digest as a single combined
message and clears it. Never fires more than once per session. Never
announces config-section changes -- only skill/plugin version bumps that
were published with a `whats_new` blurb.

What it does NOT do: deliver to gateway/Telegram sessions (`ctx.inject_message`
is CLI-only and silently no-ops there), or interrupt the user's first
message of a session (delivery is deferred to the turn boundary
specifically to avoid this).
