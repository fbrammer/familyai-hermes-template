---
name: escalation-support
familyai_version: 0.1.0
kind: plugin
description: >
  Detects "ask @frank" style escalation requests (and suggests
  escalating after repeated failures), shows the user exactly what
  will be sent, and relays it to the Phase 7 support agent once they
  confirm. Also surfaces resolutions from prior escalations.
---

# escalation-support

**Not read by Hermes.** Publish-pipeline metadata only (`kind: plugin`)
-- Hermes itself reads this directory's `plugin.yaml`.

## What it does

Registers a `pre_llm_call` hook. Each turn: polls the support agent for
any resolved prior escalations and surfaces them as context; detects an
explicit "ask frank"/"get frank" trigger phrase (`trigger_detector.py`)
or a repeated-failure "stuck" signal, and in either case tells the model
to offer/confirm with the user rather than sending anything immediately.
A user message starting `CONFIRM ESCALATION: <question>` is the
confirmed-send trigger -- at that point `escalation_client.send_case`
POSTs to the support agent, hashing the API key first (the raw key
never leaves this machine).

Requires three environment variables, set during enrollment
(`scripts/enroll_family_member.py`): `FAMILYAI_SUPPORT_AGENT_URL`,
`FAMILYAI_MEMBER_ID`, `FAMILYAI_SUPPORT_API_KEY`.

## What it does NOT do

- Never sends anything before the user explicitly confirms.
- Never escalates automatically on the "stuck" heuristic alone.
- Never bypasses the local rate limit (`rate_limiter.py`, 3/day default).

## Extending it

To change the confirmation convention (currently a plain-text
`CONFIRM ESCALATION:` prefix), update both `build_confirmation`'s
prompt text and the check in `__init__.py`'s `_on_pre_llm_call`.
