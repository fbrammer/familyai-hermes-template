---
name: sensitive-data-warn
familyai_version: 0.1.0
kind: plugin
description: >
  On-box (no network call) heuristic scan of the user's message before it
  goes to the cloud model. When something looks like it might be a Social
  Security number, credit card number, bank routing/account number,
  driver's license number, an API key/password, or medical/diagnosis
  information, gently asks the user to confirm they meant to share that --
  never blocks, never redacts.
---

# sensitive-data-warn

**Not read by Hermes.** This file exists purely as this project's own
publish-pipeline metadata (version and `kind: plugin` so the refresher
installs it to `plugins/` instead of `skills/`) -- Hermes itself only
reads this directory's `plugin.yaml`.

## What it does

Registers a `pre_llm_call` hook (see `__init__.py`). Once per turn, before
the user's message reaches the model, `detector.py` runs a short list of
regex/keyword checks against it: SSN-shaped digit groups, Luhn-checked
credit-card-shaped digit runs, 9-digit numbers near the words
"routing"/"account", driver's-license-shaped strings, common secret-key
prefixes (`sk-`, `ghp_`, etc.) or `password: ...`-shaped text, and a
medical/diagnosis keyword list.

If anything matches, the hook returns a `{"context": "..."}` injection
that tells the model (by category label only, e.g. "a credit card
number" -- never the matched text itself) to briefly and naturally check
with the user that they meant to share that before continuing, then
proceed once they respond or already show clear intent. This is
deliberately a **soft nudge inside the conversation**, not a block: the
model still receives the full original message and can act on it.

## What it does NOT do

- Does not block, redact, or modify the user's message in any way.
- Does not log or store the matched sensitive text anywhere -- only a
  category label ever leaves `detector.py`.
- Is not a compliance/DLP tool. It is a heuristic net with known false
  positives and false negatives, by design (see
  `docs/superpowers/specs/2026-08-11-sensitive-data-warn-design.md` for
  why this option was chosen over silent auto-redaction or a hard block).
- Does not call any network service -- pure local pattern matching.

## Extending it

Add a new `(label, detector_fn)` pair to `_DETECTORS` in `detector.py`.
Keep detectors simple (regex/keyword) -- this plugin is intentionally not
an ML classifier.
