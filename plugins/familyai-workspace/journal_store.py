"""Harness-neutral journal storage for FamilyAI."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable


_FILENAME_RE = re.compile(r"^\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_.+\.md$")
_FOOTER_RE = re.compile(r"<!--\s*id:\s*([^|]+?)(?:\s*\|\s*event_id:\s*([^|]+?))?\s*\|\s*project:\s*([^|]+?)\s*\|\s*kind:\s*([^|]+?)(?:\s*\|.*)?-->\s*$", re.MULTILINE)
_HEADER_RE = re.compile(r"^###\s+(\d{2}:\d{2})\s+—\s+(.+?)\s*$", re.MULTILINE)
_DAY_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE)


def _slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return value or "Entry"


def _timestamp(value: str | None = None) -> dt.datetime:
    if value:
        return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    return dt.datetime.now(dt.timezone.utc)


@contextmanager
def _file_lock(path: Path):
    lock = path.with_name(path.name + ".lock")
    started = time.monotonic()
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except FileExistsError:
            if time.monotonic() - started > 10:
                raise TimeoutError(f"could not lock {path}")
            time.sleep(0.01)
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


def _atomic_write(path: Path, content: str) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


class JournalStore:
    def __init__(self, journal_dir: Path):
        self.root = Path(journal_dir).expanduser()
        self.entries_dir = self.root / "entries"
        self.index_path = self.root / "index.jsonl"
        self.journal_path = self.root / "JOURNAL.md"
        self.entries_dir.mkdir(parents=True, exist_ok=True)

    def _lock(self, path: Path):
        return _file_lock(path)

    def _atomic_write(self, path: Path, content: str) -> None:
        _atomic_write(path, content)

    def _rows(self) -> list[dict]:
        if not self.index_path.exists():
            return []
        rows = []
        for line in self.index_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows

    def _append_index(self, row: dict) -> None:
        rows = self._rows()
        identity = row.get("event_id") or row.get("id")
        if any((existing.get("event_id") or existing.get("id")) == identity for existing in rows):
            return
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock(self.index_path):
            rows = self._rows()
            if any((existing.get("event_id") or existing.get("id")) == identity for existing in rows):
                return
            with self.index_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, sort_keys=True) + "\n")

    def _insert_markdown_index(self, filename: str, summary: str) -> None:
        content = self.journal_path.read_text(encoding="utf-8") if self.journal_path.exists() else "# Journal Index\n\n## Entries\n"
        if "## Entries" not in content:
            content = content.rstrip() + "\n\n## Entries\n"
        line = f"- [[Journal/entries/{filename[:-3]}]] — {summary}"
        if line not in content:
            marker = "## Entries"
            before, after = content.split(marker, 1)
            content = before + marker + "\n" + line + after
            self._atomic_write(self.journal_path, content.rstrip() + "\n")

    def _reserve_filename(self, base: str) -> str:
        candidate = f"{base}.md"
        if not (self.entries_dir / candidate).exists():
            return candidate
        for n in range(2, 51):
            candidate = f"{base}_{n}.md"
            if not (self.entries_dir / candidate).exists():
                return candidate
        raise RuntimeError(f"could not find a free filename for base {base}")

    def write_human_entry(
        self, subject: str, what_we_did: str, what_shipped: Iterable[str], decisions: Iterable[str],
        deferred: Iterable[str], timestamp: str | None = None,
    ) -> str:
        stamp = _timestamp(timestamp)
        entry_id = str(uuid.uuid4())
        base = f"{stamp:%Y_%m_%d_%H_%M}_{_slug(subject)}"
        body = "\n".join([
            f"# {stamp:%Y-%m-%d} — {subject}", "", "## What we did", what_we_did, "",
            "## What shipped", *[f"- {item}" for item in what_shipped], "",
            "## Decisions / constraints", *[f"- {item}" for item in decisions], "",
            "## Deferred / open", *[f"- {item}" for item in deferred], "",
            f"<!-- id: {entry_id} | kind: human | ts: {stamp:%Y-%m-%dT%H:%M:%SZ} -->", "",
        ])
        # Reserve the filename and write the entry under a lock on the entries dir,
        # so two writers with the same subject/minute never pick the same name.
        with self._lock(self.entries_dir):
            filename = self._reserve_filename(base)
            target = self.entries_dir / filename
            self._atomic_write(target, body)
        # The JOURNAL.md read-modify-write needs its own lock (not the entry lock,
        # which is per-entry and doesn't prevent two different entries from racing
        # on the same JOURNAL.md read-modify-write).
        with self._lock(self.journal_path):
            self._insert_markdown_index(filename, subject)
        self._append_index({"id": entry_id, "ts": f"{stamp:%Y-%m-%dT%H:%M:%SZ}", "project": None, "kind": "human", "title": subject, "file": f"entries/{filename}"})
        return entry_id

    def append_machine_entry(self, event_id: str, timestamp: str, project: str | None, kind: str, title: str, bullets: Iterable[str]) -> str:
        for row in self._rows():
            if row.get("event_id") == event_id:
                return row["id"]
        stamp = _timestamp(timestamp)
        entry_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"familyai:{event_id}"))
        filename = f"{stamp:%Y_%m_%d_%H_%M}_{_slug(title)}_{entry_id[:8]}.md"
        footer = f"<!-- id: {entry_id} | event_id: {event_id} | project: {project} | kind: {kind} -->"
        body = f"# {stamp:%Y-%m-%d} — {title}\n\n" + "\n".join(f"- {b}" for b in bullets) + f"\n\n{footer}\n"
        target = self.entries_dir / filename
        with self._lock(target):
            if not target.exists():
                self._atomic_write(target, body)
        self._append_index({"id": entry_id, "event_id": event_id, "ts": f"{stamp:%Y-%m-%dT%H:%M:%SZ}", "project": project, "kind": kind, "title": title, "file": f"entries/{filename}"})
        return entry_id

    def migrate_legacy(self, legacy_dir: Path) -> dict[str, int]:
        source = Path(legacy_dir) / "JOURNAL.md"
        if not source.exists():
            return {"migrated": 0, "skipped": 0}
        text = source.read_text(encoding="utf-8")
        matches = list(_HEADER_RE.finditer(text))
        migrated = skipped = 0
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            block = text[match.start():end].strip() + "\n"
            footer = _FOOTER_RE.search(block)
            if not footer:
                skipped += 1
                continue
            entry_id, event_id, project, kind = [part.strip() if part else None for part in footer.groups()]
            days = list(_DAY_RE.finditer(text[:match.start()]))
            day_value = days[-1].group(1) if days else "1970-01-01"
            hhmm = match.group(1)
            stamp = f"{day_value}T{hhmm}:00Z"
            title = match.group(2).strip()
            filename = f"{day_value.replace('-', '_')}_{hhmm.replace(':', '_')}_{_slug(title)}_{entry_id[:8]}.md"
            target = self.entries_dir / filename
            if any(row.get("id") == entry_id for row in self._rows()) or target.exists():
                skipped += 1
                continue
            self._atomic_write(target, f"# {day_value} — {title}\n\n{block}\n")
            self._append_index({"id": entry_id, "event_id": event_id, "ts": stamp, "project": project, "kind": kind or "legacy", "title": title, "file": f"entries/{filename}", "source": "legacy-hermes-stream"})
            migrated += 1
        return {"migrated": migrated, "skipped": skipped}


class SessionLogStore:
    """Storage for the silent session-log stream (renamed from auto-journal).

    Strictly disjoint from JournalStore: never touches JOURNAL.md, entries/,
    or index.jsonl. Owns <journal>/state/session-log/ instead.
    """

    def __init__(self, journal_dir: Path):
        self.root = Path(journal_dir).expanduser()
        self.log_dir = self.root / "state" / "session-log"
        self.log_path = self.log_dir / "SESSION-LOG.md"
        self.index_path = self.log_dir / "session-log.jsonl"
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def append_stream_entry(self, entry_md: str, index_row: dict) -> None:
        with _file_lock(self.log_path):
            today = dt.date.today().isoformat()
            header_line = f"## {today}"

            content = self.log_path.read_text(encoding="utf-8") if self.log_path.exists() else ""
            lines = content.splitlines()
            first_header_idx = -1
            for i, line in enumerate(lines):
                if line.strip():
                    if line.strip() == header_line:
                        first_header_idx = i
                    break

            if first_header_idx != -1:
                new_lines = lines[:first_header_idx + 1] + [entry_md.rstrip("\n")] + lines[first_header_idx + 1:]
                new_content = "\n".join(new_lines) + "\n"
            else:
                new_content = f"{header_line}\n{entry_md}"
                if content:
                    new_content += "\n" + content

            _atomic_write(self.log_path, new_content)

            with self.index_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(index_row) + "\n")
