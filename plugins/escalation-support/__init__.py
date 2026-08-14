import json
import os
import pathlib
import sys

_plugin_dir = pathlib.Path(__file__).resolve().parent
if str(_plugin_dir) not in sys.path:
    sys.path.insert(0, str(_plugin_dir))

from escalation_client import build_confirmation, poll_pending, send_case
from rate_limiter import check_and_record
from trigger_detector import detect

_STATE_DIR = pathlib.Path.home() / ".familyai" / "escalation-support"
_LEDGER_PATH = _STATE_DIR / "rate_ledger.json"
_PENDING_PATH = _STATE_DIR / "pending_cases.json"


def _config():
    return {
        "base_url": os.environ.get("FAMILYAI_SUPPORT_AGENT_URL", ""),
        "member_id": os.environ.get("FAMILYAI_MEMBER_ID", ""),
        "api_key": os.environ.get("FAMILYAI_SUPPORT_API_KEY", ""),
    }


def register(ctx):
    def _on_pre_llm_call(session_id: str, user_message: str, conversation_history: list,
                          is_first_turn: bool, model: str, platform: str, **kwargs):
        cfg = _config()
        context_parts = []

        if cfg["base_url"] and cfg["member_id"] and cfg["api_key"]:
            completed = poll_pending(cfg["base_url"], cfg["member_id"], cfg["api_key"], _PENDING_PATH)
            for case in completed:
                if case.get("state") == "resolved":
                    context_parts.append(
                        f"[escalation-support] Frank (or the support agent) resolved a prior escalation: "
                        f"{case.get('resolution', '')}. Share this with the user naturally."
                    )
                else:
                    state = case.get("state", "closed")
                    detail = (
                        "this escalation expired without a response, and they can try again"
                        if state == "expired"
                        else f"this escalation ended in state {state}; they can try again"
                    )
                    context_parts.append(f"[escalation-support] Tell the user {detail}.")

        if user_message and user_message.strip().upper().startswith("CONFIRM ESCALATION"):
            question = user_message.split(":", 1)[-1].strip() if ":" in user_message else ""
            if not question:
                context_parts.append(
                    "[escalation-support] The confirmation did not include a question. "
                    "Ask the user to clarify and retry with "
                    "\"CONFIRM ESCALATION: <question>\"."
                )
            elif cfg["base_url"]:
                rate = check_and_record(_LEDGER_PATH)
                if not rate["allowed"]:
                    context_parts.append(
                        "[escalation-support] The user has hit their daily escalation limit. "
                        "Tell them plainly and suggest trying again tomorrow or rephrasing to "
                        "see if you can help directly."
                    )
                else:
                    result = send_case(cfg["base_url"], cfg["member_id"], cfg["api_key"], question)
                    if "error" in result:
                        context_parts.append(
                            "[escalation-support] Couldn't reach the support agent right now "
                            "(network issue). Tell the user to try again shortly."
                        )
                    elif result.get("state") == "resolved":
                        context_parts.append(
                            f"[escalation-support] Resolved immediately: {result.get('resolution', '')}"
                        )
                    else:
                        _STATE_DIR.mkdir(parents=True, exist_ok=True)
                        pending = []
                        if _PENDING_PATH.exists():
                            try:
                                pending = json.loads(_PENDING_PATH.read_text())
                            except Exception:
                                pending = []
                        case_id = result.get("case_id")
                        if case_id:
                            pending.append(case_id)
                            _PENDING_PATH.write_text(json.dumps(pending))
                        context_parts.append(
                            "[escalation-support] Sent to Frank. Tell the user it's been forwarded "
                            "and they'll hear back."
                        )
        else:
            trigger = detect(user_message or "")
            if trigger["trigger"] == "explicit" and cfg["base_url"]:
                confirmation = build_confirmation(trigger["cleaned_question"] or user_message, "")
                context_parts.append(
                    f"[escalation-support] The user wants to escalate to Frank. Show them exactly "
                    f"what will be sent:\n\n{confirmation['payload_preview']}\n\n"
                    "Ask them to confirm by replying with a message starting "
                    "\"CONFIRM ESCALATION: <question>\". Do not send anything until they do."
                )
            elif trigger["trigger"] == "suggested":
                context_parts.append(
                    "[escalation-support] You've been stuck on this for a couple of tries. "
                    "Naturally offer the user the option to escalate to Frank -- do not send "
                    "anything unless they explicitly agree."
                )

        if not context_parts:
            return None
        return {"context": "\n\n".join(context_parts)}

    ctx.register_hook("pre_llm_call", _on_pre_llm_call)
