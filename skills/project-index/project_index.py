from __future__ import annotations

import json
import pathlib
import re
from dataclasses import dataclass
from typing import Any, List, Tuple


class UnreliableIndexError(Exception):
    """Raised when a project index file is too unreliable to use."""


@dataclass
class ProjectEntry:
    name: str
    path: str
    purpose: str
    keywords: List[str]
    updated: str
    archived: bool = False


MATCH_FLOOR = 0.2
AMBIGUITY_MARGIN = 0.1
ACTIVE_PROJECT_OVERRIDE = 0.5


def parse_index(path: pathlib.Path) -> List[ProjectEntry]:
    if not path.exists():
        return []

    total_non_blank = 0
    failed_parse = 0
    entries: List[ProjectEntry] = []

    pattern = re.compile(
        r"^- \*\*(?P<name>[^*]+)\*\* — `(?P<path>[^`]+)` — (?P<purpose>.+?)\. "
        r"\[keywords: (?P<keywords>[^\]]*)\](?P<archived_flag> \[ARCHIVED\])? "
        r"\(updated (?P<updated>[\d-]+)\)\s*$"
    )

    content = path.read_text()
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        total_non_blank += 1
        match = pattern.fullmatch(stripped)

        if not match:
            failed_parse += 1
            continue

        name = match.group("name")
        file_path = match.group("path")
        purpose = match.group("purpose")
        keywords_str = match.group("keywords")
        archived = match.group("archived_flag") is not None
        updated = match.group("updated")

        keywords = [kw.strip() for kw in keywords_str.split(",")] if keywords_str else []
        keywords = [kw for kw in (k.strip() for k in keywords) if kw]

        entries.append(
            ProjectEntry(
                name=name,
                path=file_path,
                purpose=purpose,
                keywords=keywords,
                updated=updated,
                archived=archived,
            )
        )

    if total_non_blank > 0 and (failed_parse / total_non_blank) > 0.5:
        raise UnreliableIndexError(
            f"Index file has {failed_parse}/{total_non_blank} lines that failed to parse"
        )

    return entries


def should_route(event_context: dict) -> str:
    kind = event_context.get("kind")
    identity_confidence = event_context.get("identity_confidence", 0.0)

    if kind == "user_directed_at_existing_directory":
        return "none"

    if kind in ("explicit_save", "multi_session_task", "add_to_existing"):
        return "route" if identity_confidence >= 0.5 else "inbox"

    if kind in ("draft_in_conversation", "transient_research", "one_off_question"):
        return "none"

    return "none"


def score_candidates(
    request_keywords: List[str],
    request_text: str,
    entries: List[ProjectEntry],
    active_project: str | None = None,
    now_iso_date: str | None = None,
) -> List[Tuple[ProjectEntry, float]]:
    scored: List[Tuple[ProjectEntry, float]] = []

    for entry in entries:
        request_keywords_set = set(k.lower() for k in request_keywords)
        entry_keywords_set = set(k.lower() for k in entry.keywords)

        keyword_overlap = (
            len(request_keywords_set & entry_keywords_set) / max(len(entry.keywords), 1)
            if entry.keywords
            else 0.0
        )
        keyword_overlap = min(keyword_overlap, 1.0)

        text_mention = 1.0 if (
            entry.name.lower() in request_text.lower() or
            entry.path.lower() in request_text.lower()
        ) else 0.0

        recency = 1.0 if (now_iso_date is not None and entry.updated == now_iso_date) else 0.0

        active_boost = 1.0 if (active_project is not None and entry.name == active_project) else 0.0

        raw_score = (
            0.5 * keyword_overlap +
            0.2 * text_mention +
            0.15 * recency +
            0.15 * active_boost
        )

        final_score = raw_score * 0.6 if entry.archived else raw_score

        scored.append((entry, final_score))

    scored.sort(key=lambda x: x[1], reverse=True)

    return scored


def adjudicate(
    scored_candidates: List[Tuple[ProjectEntry, float]],
    top_is_active_project: bool = False,
) -> str:
    if not scored_candidates:
        return "below_floor"

    top_score = scored_candidates[0][1]

    if top_score < MATCH_FLOOR:
        return "below_floor"

    if len(scored_candidates) >= 2:
        score_diff = top_score - scored_candidates[1][1]
        if score_diff < AMBIGUITY_MARGIN:
            if top_is_active_project and top_score >= ACTIVE_PROJECT_OVERRIDE:
                return "confident"
            return "ambiguous"

    return "confident"


def write_manifest(
    operation_id: str,
    created_paths: List[str],
    modified_paths: List[str],
    prior_locations: List[str],
    external_effects: List[str],
    project: str,
    manifests_dir: pathlib.Path,
) -> None:
    manifests_dir.mkdir(parents=True, exist_ok=True)
    manifests_file = manifests_dir / "manifests.jsonl"

    entry = {
        "operation_id": operation_id,
        "created_paths": created_paths,
        "modified_paths": modified_paths,
        "prior_locations": prior_locations,
        "external_effects": external_effects,
        "project": project,
    }

    with open(manifests_file, "a") as f:
        f.write(json.dumps(entry) + "\n")

    with open(manifests_file, "r") as f:
        lines = f.readlines()

    if len(lines) > 10:
        with open(manifests_file, "w") as f:
            for line in lines[-10:]:
                f.write(line)


def move_created_paths(
    operation_id: str,
    manifests_dir: pathlib.Path,
    move_fn,
) -> List[str]:
    manifests_file = manifests_dir / "manifests.jsonl"

    if not manifests_file.exists():
        return []

    with open(manifests_file, "r") as f:
        lines = [json.loads(line.strip()) for line in f if line.strip()]

    matching_manifests = [
        line for line in lines if line.get("operation_id") == operation_id
    ]

    if not matching_manifests:
        return []

    target_manifest = matching_manifests[-1]
    created_paths = target_manifest.get("created_paths", [])

    for path in created_paths:
        move_fn(path)

    return created_paths


def reconcile(
    entries: List[ProjectEntry],
    approved_roots: List[str],
    path_exists_fn,
    get_identity_fn,
) -> List[dict]:
    results: List[dict] = []

    for entry in entries:
        if not any(entry.path.startswith(root) for root in approved_roots):
            continue

        if not path_exists_fn(entry.path):
            try:
                identity = get_identity_fn(entry.path)
            except OSError:
                continue

            if identity is None:
                results.append({"entry": entry.name, "status": "missing"})

    return results
