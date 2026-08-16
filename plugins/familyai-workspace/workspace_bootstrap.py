"""Silent, idempotent FamilyAI workspace and journal bootstrap."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

try:
    from journal.journal_store import JournalStore
except ImportError:  # packaged plugin mirror
    from journal_store import JournalStore


_HOW_TO_JOURNAL_ASSET = Path(__file__).resolve().parent / "assets" / "HOW_TO_JOURNAL.md"
_WORKSPACE_ASSET_ROOT = Path(__file__).resolve().parent / "assets" / "file-folder-method"
HOW_TO_JOURNAL = (
    _HOW_TO_JOURNAL_ASSET.read_text(encoding="utf-8")
    if _HOW_TO_JOURNAL_ASSET.exists()
    else "# How to journal\n\nSay `journal` to create a written record.\n"
)

_ROOT_GUIDANCE_ASSETS = {
    "CLAUDE.template.md": "CLAUDE.md",
    "AGENT.template.md": "AGENT.md",
    "ROUTING.template.md": "ROUTING.md",
}
_METHOD_ASSETS = {
    "README.md": "README.md",
    "templates/CLAUDE.template.md": "templates/CLAUDE.md",
    "templates/AGENT.template.md": "templates/AGENT.md",
    "templates/ROUTING.template.md": "templates/ROUTING.md",
}
_WORKSPACE_MARKER = b"<!-- familyai:workspace-basics:start -->"


def default_root(home: Path) -> Path:
    return Path(home).expanduser() / "AI"


def _migrate_documents_layout(home: Path, root: Path) -> str:
    documents = Path(home) / "Documents" / "AI"
    if root.is_symlink():
        if not documents.exists() or root.resolve() != documents.resolve():
            return "refused_existing_symlink"
        root.unlink()
        root.mkdir(parents=True, exist_ok=True)
        for child in list(documents.iterdir()):
            shutil.move(str(child), str(root / child.name))
        documents.rmdir()
        documents.symlink_to(root, target_is_directory=True)
        return "migrated_from_documents"
    if root.exists() and documents.exists() and root.resolve() != documents.resolve():
        return "refused_conflicting_directories"
    if not root.exists() and documents.exists():
        root.mkdir(parents=True, exist_ok=True)
        for child in list(documents.iterdir()):
            shutil.move(str(child), str(root / child.name))
        documents.rmdir()
        documents.symlink_to(root, target_is_directory=True)
        return "migrated_from_documents"
    root.mkdir(parents=True, exist_ok=True)
    return "already_correct" if root.exists() else "created_fresh"


def _copy_legacy_state(old_state: Path, state: Path) -> None:
    old_sessions = old_state / "sessions"
    new_sessions = state / "session-ledger"
    if old_sessions.is_dir():
        new_sessions.mkdir(parents=True, exist_ok=True)
        for source in old_sessions.iterdir():
            target = new_sessions / source.name
            if source.is_file() and not target.exists():
                shutil.copy2(source, target)
    old_reflect = old_state / "journal" / "reflect-state.json"
    new_reflect = state / "reflect-state.json"
    if old_reflect.exists() and not new_reflect.exists():
        shutil.copy2(old_reflect, new_reflect)


def _has_symlinked_ancestor(target: Path, root: Path) -> bool:
    try:
        target.relative_to(root)
    except ValueError:
        return True
    parent = target.parent
    while parent != root:
        if parent.is_symlink():
            return True
        parent = parent.parent
    return False


def _seed_file(source: Path, target: Path, root: Path) -> None:
    if _has_symlinked_ancestor(target, root):
        return
    if target.exists() or target.is_symlink():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())


def _install_root_guidance(source: Path, target: Path, root: Path) -> None:
    if target.is_symlink() or (target.exists() and not target.is_file()):
        return
    if not target.exists():
        _seed_file(source, target, root)
        return
    current = target.read_bytes()
    if _WORKSPACE_MARKER in current:
        return
    separator = b"" if not current else (b"\n" if current.endswith(b"\n") else b"\n\n")
    with target.open("ab") as stream:
        stream.write(separator + source.read_bytes())


def _install_workspace_method(root: Path) -> None:
    for directory in ("Projects", "FILE-IN", "FILE-OUT"):
        (root / directory).mkdir(parents=True, exist_ok=True)
    for source_name, target_name in _ROOT_GUIDANCE_ASSETS.items():
        _install_root_guidance(_WORKSPACE_ASSET_ROOT / source_name, root / target_name, root)
    method = root / "FileFolderMethod"
    for source_name, target_name in _METHOD_ASSETS.items():
        _seed_file(_WORKSPACE_ASSET_ROOT / source_name, method / target_name, root)


def bootstrap(home: Path | None = None, old_state: Path | None = None) -> dict:
    """Bootstrap without prompts, stdout, or dependency on an assistant harness."""
    home = Path(home or Path.home())
    root = default_root(home)
    try:
        layout_status = _migrate_documents_layout(home, root)
        _install_workspace_method(root)
        journal = root / "Journal"
        state = journal / "state"
        journal.mkdir(parents=True, exist_ok=True)
        (journal / "entries").mkdir(exist_ok=True)
        (state / "session-ledger").mkdir(parents=True, exist_ok=True)
        (state / "pending").mkdir(exist_ok=True)
        how_to = journal / "HOW_TO_JOURNAL.md"
        if not how_to.exists():
            how_to.write_text(HOW_TO_JOURNAL, encoding="utf-8")
        journal_file = journal / "JOURNAL.md"
        if not journal_file.exists():
            journal_file.write_text("# Journal Index\n\n## Entries\n", encoding="utf-8")
        old_state = Path(old_state) if old_state else home / ".hermes" / "familyai"
        _copy_legacy_state(old_state, state)
        migration = JournalStore(journal).migrate_legacy(old_state / "journal")
        marker = state / "migration.json"
        marker.write_text(json.dumps({"version": 1, "legacy": str(old_state / "journal"), "migration": migration}), encoding="utf-8")
        return {"status": "bootstrapped", "root": str(root), "layout": layout_status, "migration": migration}
    except Exception as exc:  # fail open for the assistant/session
        return {"status": "failed_open", "root": str(root), "error": type(exc).__name__}


if __name__ == "__main__":
    bootstrap()
