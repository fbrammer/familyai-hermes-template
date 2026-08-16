"""Builds the workspace directive injected into a session's system context."""
from __future__ import annotations


def build_directive(contract: dict | None) -> str | None:
    if not contract:
        return None
    root = contract["root"]
    projects = contract["projects"]
    file_in = contract["file_in"]
    file_out = contract["file_out"]
    journal = contract["journal"]
    return (
        f"Workspace basics for this user:\n"
        f"- The working root is {root}. Anything file-based defaults there.\n"
        f"- \"Start a project\" means create {projects}/<Title_Case_Slug>/ and work inside it.\n"
        f"- User drop-offs live in {file_in}; deliverables go in {file_out}.\n"
        f"- The user's Journal is at {journal}. If the user says `journal` (alone, "
        f"or \"write a journal entry\", \"journal this\"), follow {journal}/HOW_TO_JOURNAL.md "
        f"and use the shared journal writer. Never invent another journal location or format."
    )
