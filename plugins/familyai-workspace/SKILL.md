---
name: familyai-workspace
familyai_version: 0.1.0
kind: plugin
whats_new: Journal and journal state now live under ~/AI and migrate silently during refresh.
description: >
  Bootstraps the user-owned workspace and journal. Journal data is independent
  of the assistant harness and survives removal of Hermes.
---

# familyai-workspace

This plugin is an optional Hermes adapter over the portable FamilyAI workspace
and journal bootstrap. The canonical journal lives under `~/AI/Journal/`; do
not create or use a second harness-owned journal location.
