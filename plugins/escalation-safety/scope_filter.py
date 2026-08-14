"""Topic-scope classification for FamilyAI escalations. Deliberately a
keyword/phrase matcher, not an LLM judgment call -- fast, predictable,
and auditable. Fail-closed: any internal error blocks rather than
passing through (see Global Constraints in the Phase 7 plan)."""

import re

_CROSS_MEMBER_RE = re.compile(
    r"\b(?:ask|tell|what did|show me)\b.{0,30}\b(?:michael|vickie|"
    r"another family member|other family member)\b",
    re.IGNORECASE,
)

_CREDENTIAL_KEYWORD_RE = re.compile(
    r"\b(?:password|passwd|api[_\s-]?key|secret|recovery code|private key)\b\s*[:=]?\s*\S{0,20}",
    re.IGNORECASE,
)

_OUT_OF_SCOPE_KEYWORDS = {
    "looks like medical/legal/financial advice, not FamilyAI support": (
        "chest pain", "diagnosis", "prescri", "refinance", "mortgage",
        "lawsuit", "divorce", "custody", "tax advice", "invest",
    ),
}

_IN_SCOPE_CATEGORIES = (
    ("installation", ("onboarding wizard", "install", "setup", "git setup")),
    ("configuration", ("config", "reconnect telegram", "telegram", "option")),
    ("troubleshooting", ("stopped responding", "error", "broken", "not working", "stuck")),
    ("usage", ("how do i", "how does", "what does")),
)


def classify(text: str) -> dict:
    try:
        return _classify(text)
    except Exception:
        return {
            "in_scope": False,
            "category": None,
            "blocked_reason": "safety check failed, blocked to be safe",
            "mentions_other_member": False,
        }


def _classify(text: str) -> dict:
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    if not text or not text.strip():
        return {
            "in_scope": False,
            "category": None,
            "blocked_reason": "empty message",
            "mentions_other_member": False,
        }

    lowered = text.lower()

    if _CROSS_MEMBER_RE.search(text):
        return {
            "in_scope": False,
            "category": None,
            "blocked_reason": "looks like a request involving another family member's information",
            "mentions_other_member": True,
        }

    if _CREDENTIAL_KEYWORD_RE.search(text):
        return {
            "in_scope": False,
            "category": None,
            "blocked_reason": "looks like it contains a credential or secret",
            "mentions_other_member": False,
        }

    for reason, keywords in _OUT_OF_SCOPE_KEYWORDS.items():
        if any(kw in lowered for kw in keywords):
            return {
                "in_scope": False,
                "category": None,
                "blocked_reason": reason,
                "mentions_other_member": False,
            }

    for category, keywords in _IN_SCOPE_CATEGORIES:
        if any(kw in lowered for kw in keywords):
            return {
                "in_scope": True,
                "category": category,
                "blocked_reason": None,
                "mentions_other_member": False,
            }

    return {
        "in_scope": False,
        "category": None,
        "blocked_reason": "not clearly a FamilyAI support topic",
        "mentions_other_member": False,
    }
