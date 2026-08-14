---
name: escalation-safety
familyai_version: 0.1.0
kind: plugin
description: >
  Shared, fail-closed topic-scope classifier used by both legs of the
  Phase 7 escalation relay. Keeps escalations limited to FamilyAI
  support topics and blocks attempts to route content to or about
  another family member.
---

# escalation-safety

**Not read by Hermes as a hook plugin** -- registers no hooks. It exists
so `escalation-support` (family side) and the support agent
(`scripts/support_agent/`) both import the exact same `scope_filter.classify()`
logic instead of maintaining two copies that could drift apart.

## What it does

`scope_filter.classify(text)` returns whether a message is in scope for
FamilyAI support (installation, configuration, troubleshooting, usage),
and if not, a short user-facing reason. It never raises: any internal
error is treated as out-of-scope (fail-closed, per
`docs/superpowers/specs/2026-08-12-escalation-support-agent-design.md`).

## Extending it

Add keywords to `_IN_SCOPE_CATEGORIES` or `_OUT_OF_SCOPE_KEYWORDS` in
`scope_filter.py`. Keep it a keyword/phrase matcher, not an LLM call --
this must run identically and fast on both sides of the relay.
