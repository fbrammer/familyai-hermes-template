# FamilyAI Hermes Template

Sanitized starting-point Hermes configuration for FamilyAI onboarding:
staggered fallback model tiers, auxiliary (background/utility) model
routing, delegation, and MoA (mixture-of-agents) settings.

**This repo is auto-published.** A weekly job on the builder's own
machine re-exports and sanitizes these four sections
(`fallback_providers`, `auxiliary`, `delegation`, `moa`) from their own
live Hermes config and publishes the result here as `manifest.json`.
Nothing else lives here on purpose -- no personal data, no API keys
(only env-var references), no unrelated config sections.

`refresher.py` and `familyai_config_validate.py` are the scripts an
onboarded user's own machine runs daily to keep its config in sync with
`manifest.json` -- see the FamilyAI project's design spec for the full
architecture (builder-side publisher -> this repo -> end-user refresher).

First publish completed 2026-07-28. The weekly publisher cron job runs
every Sunday at 15:00 (builder's local time) and only writes an update
when the content actually changed.
