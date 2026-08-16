---
name: familyai-workspace
familyai_version: 0.2.0
kind: plugin
whats_new: Adds a minimal, user-preserving FileFolderMethod under ~/AI.
description: >
  Bootstraps the user-owned workspace and journal. Journal data is independent
  of the assistant harness and survives removal of Hermes.
---

# familyai-workspace

This plugin is an optional Hermes adapter over the portable FamilyAI workspace
and journal bootstrap. The canonical journal lives under `~/AI/Journal/`; do
not create or use a second harness-owned journal location. Root workspace
instructions and project templates live under `~/AI` and preserve user edits.
