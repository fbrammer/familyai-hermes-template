"""HTTP client for talking to the Phase 7 support agent. Every send
requires the caller to have already run the confirmation step
(build_confirmation) -- this module does not decide whether to send,
only how."""

import hashlib
import json
from pathlib import Path

import requests

_TERMINAL_STATES = {"resolved", "expired", "cancelled", "failed", "blocked"}


def build_confirmation(cleaned_question: str, recent_context: str) -> dict:
    preview = f'This will be sent to Frank via the support agent:\n\n"{cleaned_question}"'
    if recent_context:
        preview += f"\n\n(plus recent context: {recent_context})"
    return {"payload_preview": preview, "question": cleaned_question}


def send_case(base_url: str, member_id: str, api_key: str, question: str) -> dict:
    api_key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    try:
        resp = requests.post(
            f"{base_url}/case",
            json={"member_id": member_id, "api_key_hash": api_key_hash, "question": question},
            timeout=15,
        )
        body = resp.json()
        if not 200 <= resp.status_code < 300:
            return {"error": body.get("detail", f"support agent returned HTTP {resp.status_code}")}
        return body
    except Exception as exc:
        return {"error": str(exc)}


def poll_pending(base_url: str, member_id: str, api_key: str, pending_path: Path) -> list[dict]:
    if not pending_path.exists():
        return []

    try:
        case_ids = json.loads(pending_path.read_text())
    except Exception:
        return []

    api_key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    completed = []
    still_pending = []

    for case_id in case_ids:
        try:
            resp = requests.get(
                f"{base_url}/case/{case_id}",
                params={"member_id": member_id, "api_key_hash": api_key_hash},
                timeout=10,
            )
            case = resp.json()
        except Exception:
            still_pending.append(case_id)
            continue

        if case.get("state") in _TERMINAL_STATES:
            completed.append(case)
        else:
            still_pending.append(case_id)

    pending_path.write_text(json.dumps(still_pending))
    return completed
