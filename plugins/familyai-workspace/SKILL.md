---
name: familyai-workspace
familyai_version: 0.3.0
kind: plugin
whats_new: >
  Writes a machine-readable workspace.json contract and injects a short
  workspace directive into the session's system context at session start
  (working root, project/journal locations, and the "journal" trigger word).
description: >
  Bootstraps the user-owned workspace and journal. Journal data is independent
  of the assistant harness and survives removal of Hermes.
---

# familyai-workspace

This plugin is an optional Hermes adapter over the portable FamilyAI workspace
and journal bootstrap. The canonical journal lives under `~/AI/Journal/`; do
not create or use a second harness-owned journal location. Root workspace
instructions and project templates live under `~/AI` and preserve user edits.

On session start, the plugin runs `bootstrap()` (idempotent, fails open),
reads the resulting `workspace.json` contract, and injects a compact
directive on the next model turn stating the working root, project/journal
locations, and that the word `journal` triggers the human journal writer.
If the contract is missing (bootstrap failed open), nothing is injected and
the session proceeds normally.

## Known gaps

- **Windows is untested.** No known FamilyAI install runs on Windows today.
  The Desktop/Documents discoverability link tries a directory junction
  (`mklink /J`, no elevation required) first, and falls back to a symlink
  (which may require Developer Mode) if that fails. If both fail, the link
  is simply skipped -- the workspace itself is still fully usable at `~/AI`,
  only the shortcut is missing.
- Documents redirected into OneDrive (common on managed Windows machines) is
  an untested case for the junction/symlink fallback.
- There is no Desktop link yet (spec section A2 step 5) and no launcher
  rewrite yet (step 6) -- only the Documents link is created today.
