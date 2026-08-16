# FamilyAI FileFolderMethod

This is a small file-and-folder method for keeping work under `~/AI` understandable to both people and AI assistants.

## The three governing files

- `CLAUDE.md` is the entry point. Keep it short and point it to `AGENT.md`.
- `AGENT.md` explains the folder's purpose, working rules, and what “done” means.
- `ROUTING.md` maps requests and important files to real folders.

The normal read order is `CLAUDE.md` → `AGENT.md` → `ROUTING.md`.

## When a folder needs these files

Use the three-file pattern for the `~/AI` root and for a project or subfolder that has its own purpose, workflow, or routing decisions. Ordinary storage folders do not need instruction files.

## Create a project

1. Create `~/AI/Projects/<Project_Name>/`.
2. Copy the files from [templates](./templates/) into the project folder.
3. Replace the bracketed fields in `AGENT.md` with the project's real purpose, owner, workflow, completion rule, and output location.
4. Replace the example rows in `ROUTING.md` with links to folders that actually exist.
5. Keep `CLAUDE.md` minimal.
6. Update routing whenever important files or folders move.

FamilyAI may create missing root guidance, but it does not automatically add instruction files to every folder and it does not overwrite customized project files.
