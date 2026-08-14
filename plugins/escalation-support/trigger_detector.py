"""Detects the explicit "ask Frank" trigger phrase, and separately
suggests (never auto-sends) escalation after repeated failures. Per the
Phase 7 design spec: explicit trigger always escalates (after
confirmation, handled elsewhere); a stuck heuristic may only *suggest*,
never escalate silently on judgment alone."""

import re

_EXPLICIT_RE = re.compile(
    r"^\s*(?:ask\s+@?frank\b|get\s+frank\b)\s*,?\s*(.*)$",
    re.IGNORECASE,
)

_SUGGEST_THRESHOLD = 2


def detect(user_message: str, recent_failure_count: int = 0) -> dict:
    if not user_message:
        return {"trigger": None, "cleaned_question": None}

    match = _EXPLICIT_RE.match(user_message.strip())
    if match:
        cleaned = match.group(1).strip()
        return {"trigger": "explicit", "cleaned_question": cleaned or None}

    if recent_failure_count >= _SUGGEST_THRESHOLD:
        return {"trigger": "suggested", "cleaned_question": None}

    return {"trigger": None, "cleaned_question": None}
