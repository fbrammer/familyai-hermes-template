"""Silent, idempotent FamilyAI workspace and journal bootstrap."""
from __future__ import annotations

import datetime as _dt
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


WORKSPACE_JSON_FILENAME = "workspace.json"
_WORKSPACE_CONTRACT_VERSION = 1


def default_root(home: Path) -> Path:
    return Path(home).expanduser() / "AI"


def resolve_layout(root: Path, migrated_from: Path | None = None, documents_link: str | None = None) -> dict:
    root = Path(root)
    journal = root / "Journal"
    return {
        "version": _WORKSPACE_CONTRACT_VERSION,
        "root": str(root),
        "journal": str(journal),
        "journal_state": str(journal / "state"),
        "projects": str(root / "Projects"),
        "file_in": str(root / "FILE-IN"),
        "file_out": str(root / "FILE-OUT"),
        "bootstrapped_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "migrated_from": str(migrated_from) if migrated_from else None,
        "documents_link": documents_link,
    }


def save_contract(state_dir: Path, contract: dict) -> None:
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / WORKSPACE_JSON_FILENAME
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(contract), encoding="utf-8")
    os.replace(tmp, path)


def load_contract(state_dir: Path) -> dict | None:
    path = Path(state_dir) / WORKSPACE_JSON_FILENAME
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict) or data.get("version") != _WORKSPACE_CONTRACT_VERSION:
        return None
    return data


def is_bootstrapped(state_dir: Path, root: Path) -> bool:
    contract = load_contract(state_dir)
    if contract is None:
        return False
    return Path(contract.get("root", "")) == Path(root) and Path(root).exists()


def _link_directory(link_path: Path, target: Path) -> str:
    """Create a discoverability link. Never raises -- the content move is the
    load-bearing part of a migration, the link is a convenience on top of it.

    Returns 'junction' (Windows, mklink /J succeeded), 'symlink' (non-Windows,
    or a Windows fallback after the junction attempt failed), or 'unlinked'
    (every attempt failed -- the workspace itself is still fully usable).
    """
    if os.name == "nt":
        import subprocess
        try:
            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link_path), str(target)],
                check=False, capture_output=True, text=True,
            )
            if result.returncode == 0:
                return "junction"
        except OSError:
            pass
        try:
            link_path.symlink_to(target, target_is_directory=True)
            return "symlink"
        except OSError:
            return "unlinked"
    try:
        link_path.symlink_to(target, target_is_directory=True)
        return "symlink"
    except OSError:
        return "unlinked"


def _migrate_documents_layout(home: Path, root: Path) -> tuple[str, str | None]:
    documents = Path(home) / "Documents" / "AI"
    if root.is_symlink():
        if not documents.exists() or root.resolve() != documents.resolve():
            return "refused_existing_symlink", None
        root.unlink()
        root.mkdir(parents=True, exist_ok=True)
        for child in list(documents.iterdir()):
            shutil.move(str(child), str(root / child.name))
        documents.rmdir()
        link_result = _link_directory(documents, root)
        return "migrated_from_documents", link_result
    if root.exists() and documents.exists() and root.resolve() != documents.resolve():
        return "refused_conflicting_directories", None
    if not root.exists() and documents.exists():
        root.mkdir(parents=True, exist_ok=True)
        for child in list(documents.iterdir()):
            shutil.move(str(child), str(root / child.name))
        documents.rmdir()
        link_result = _link_directory(documents, root)
        return "migrated_from_documents", link_result
    root.mkdir(parents=True, exist_ok=True)
    return ("already_correct" if root.exists() else "created_fresh"), None


def _copy_legacy_state(old_state: Path, state: Path) -> None:
    old_sessions = old_state / "sessions"
    new_sessions = state / "sessions"
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


def migrate_session_ledger_dir(state: Path) -> dict:
    """Forward-migrate the old (incorrectly named) session-ledger dir into sessions/.

    ledger.py and session_end.py read/write <journal>/state/sessions/ directly; an
    earlier bootstrap version created state/session-ledger/ instead, which those
    consumers never read. Never overwrite an existing sessions/ file -- skip and
    report instead.
    """
    old_dir = state / "session-ledger"
    new_dir = state / "sessions"
    moved = 0
    skipped = 0
    if old_dir.is_dir():
        new_dir.mkdir(parents=True, exist_ok=True)
        for source in list(old_dir.iterdir()):
            target = new_dir / source.name
            if not source.is_file():
                continue
            if target.exists():
                skipped += 1
                continue
            shutil.move(str(source), str(target))
            moved += 1
        if skipped == 0 and not any(old_dir.iterdir()):
            old_dir.rmdir()
    return {"moved": moved, "skipped": skipped}


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
        layout_status, documents_link = _migrate_documents_layout(home, root)
        migrated_from = (home / "Documents" / "AI") if layout_status == "migrated_from_documents" else None
        _install_workspace_method(root)
        journal = root / "Journal"
        state = journal / "state"
        journal.mkdir(parents=True, exist_ok=True)
        (journal / "entries").mkdir(exist_ok=True)
        (state / "sessions").mkdir(parents=True, exist_ok=True)
        (state / "pending").mkdir(exist_ok=True)
        how_to = journal / "HOW_TO_JOURNAL.md"
        if not how_to.exists():
            how_to.write_text(HOW_TO_JOURNAL, encoding="utf-8")
        journal_file = journal / "JOURNAL.md"
        if not journal_file.exists():
            journal_file.write_text("# Journal Index\n\n## Entries\n", encoding="utf-8")
        old_state = Path(old_state) if old_state else home / ".hermes" / "familyai"
        session_ledger_migration = migrate_session_ledger_dir(state)
        _copy_legacy_state(old_state, state)
        migration = JournalStore(journal).migrate_legacy(old_state / "journal")
        marker = state / "migration.json"
        marker.write_text(json.dumps({
            "version": 2,
            "legacy": str(old_state / "journal"),
            "migration": migration,
            "session_ledger": session_ledger_migration,
        }), encoding="utf-8")
        contract = resolve_layout(root, migrated_from=migrated_from, documents_link=documents_link)
        save_contract(old_state, contract)
        return {
            "status": "bootstrapped", "root": str(root), "layout": layout_status,
            "migration": migration, "documents_link": documents_link,
        }
    except Exception as exc:  # fail open for the assistant/session
        return {"status": "failed_open", "root": str(root), "error": type(exc).__name__}


if __name__ == "__main__":
    bootstrap()
