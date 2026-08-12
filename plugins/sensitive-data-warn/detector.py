"""Heuristic, on-box (no network call) scan for sensitive-looking content in a
user's message. Pattern list, not a classifier -- deliberately simple and
easy to extend. False positives are expected and fine: this feeds a soft
in-conversation heads-up, never a hard block.

Each detector returns a category label (never the raw matched text) so
callers can tell the model "this looks like it might contain an SSN"
without ever putting the actual sensitive substring into a prompt.
"""

import re

# --- Luhn check, used to cut down credit-card-pattern false positives ---


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b|\b\d{3}\s\d{2}\s\d{4}\b")

_CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")

_ROUTING_CONTEXT_RE = re.compile(
    r"\b(?:routing|account|acct)\b.{0,20}\b\d{9}\b|\b\d{9}\b.{0,20}\b(?:routing|account|acct)\b",
    re.IGNORECASE,
)

_DRIVERS_LICENSE_RE = re.compile(
    r"\b(?:driver'?s?\s*licen[sc]e|dl\s*#?)\D{0,10}[A-Z]{0,2}\d{6,9}\b", re.IGNORECASE
)

_SECRET_PREFIXES = (
    "sk-", "ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_",
    "xox", "AKIA", "AIza", "sk_live_", "sk_test_", "pk_live_",
)

_SECRET_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(p) for p in _SECRET_PREFIXES) + r")[A-Za-z0-9_\-]{10,}\b"
)

_GENERIC_SECRET_KEYWORD_RE = re.compile(
    r"\b(?:password|passwd|api[_\s-]?key|secret|token)\b\s*[:=]\s*\S{6,}", re.IGNORECASE
)

_MEDICAL_KEYWORDS = (
    "diagnosed with", "diagnosis", "biopsy", "chemotherapy", "chemo",
    "hiv positive", "hiv+", "std ", "sti ", "std/sti", "depression",
    "anxiety disorder", "bipolar", "schizophrenia", "suicidal",
    "prescription for", "prescribed", "cancer", "std test", "medical record",
    "genetic test", "mental health diagnosis",
)


def _find_ssn(text: str) -> bool:
    for m in _SSN_RE.finditer(text):
        digits = re.sub(r"[\s-]", "", m.group())
        if len(digits) == 9:
            return True
    return False


def _find_card(text: str) -> bool:
    for m in _CARD_RE.finditer(text):
        digits = re.sub(r"[ -]", "", m.group())
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            return True
    return False


def _find_routing(text: str) -> bool:
    return bool(_ROUTING_CONTEXT_RE.search(text))


def _find_drivers_license(text: str) -> bool:
    return bool(_DRIVERS_LICENSE_RE.search(text))


def _find_secret(text: str) -> bool:
    return bool(_SECRET_RE.search(text)) or bool(_GENERIC_SECRET_KEYWORD_RE.search(text))


def _find_medical(text: str) -> bool:
    lowered = text.lower()
    return any(kw in lowered for kw in _MEDICAL_KEYWORDS)


# Ordered (category label, detector fn). First match per category is enough;
# multiple categories may match the same message.
_DETECTORS = (
    ("a Social Security number", _find_ssn),
    ("a credit card number", _find_card),
    ("a bank routing/account number", _find_routing),
    ("a driver's license number", _find_drivers_license),
    ("an API key, password, or other secret", _find_secret),
    ("medical/diagnosis information", _find_medical),
)


def scan(text: str) -> list[str]:
    """Return the list of matched category labels (may be empty). Never
    returns or logs the matched substrings themselves."""
    if not text:
        return []
    hits = []
    for label, fn in _DETECTORS:
        try:
            if fn(text):
                hits.append(label)
        except Exception:
            # A detector misbehaving should never break the turn.
            continue
    return hits
