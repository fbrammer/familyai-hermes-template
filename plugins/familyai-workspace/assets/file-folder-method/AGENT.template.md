<!-- familyai:workspace-basics:start -->
# FamilyAI Workspace Instructions

## Purpose

`~/AI` is the home for your projects, journal, incoming files, and finished work. Keep FamilyAI-created user content here so it remains available independently of any assistant application.

## Read order

Use this order when an assistant starts in this workspace:

1. `CLAUDE.md` — the short entry point.
2. `AGENT.md` — the instructions for the current folder.
3. `ROUTING.md` — the map to the right folder.

In short: **CLAUDE.md → AGENT.md → ROUTING.md**.

## Where things go

- `Projects/` — one folder per ongoing project.
- `Journal/` — journal entries and their index.
- `FILE-IN/` — files you want the assistant to work on.
- `FILE-OUT/` — completed files for you to retrieve.
- `FileFolderMethod/` — the guide and templates for organizing new projects.

## Starting a project

Create the project under `~/AI/Projects/<Project_Name>/`. Give it its own `CLAUDE.md`, `AGENT.md`, and `ROUTING.md` by copying the templates in `FileFolderMethod/templates/`, then tailor the purpose and routes to that project.

Do not place instruction files in every folder automatically. Add them only where a folder has its own purpose or routing decisions.

## Working rules

- Preserve existing user files and instructions.
- Read before editing and make the smallest useful change.
- Keep `CLAUDE.md` short; put real instructions in `AGENT.md`.
- Keep `ROUTING.md` synchronized with folders that actually exist.
- Verify files and links against the real filesystem before declaring work complete.
<!-- familyai:workspace-basics:end -->
