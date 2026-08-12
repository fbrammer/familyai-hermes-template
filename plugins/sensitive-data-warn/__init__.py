import pathlib
import sys

_plugin_dir = pathlib.Path(__file__).resolve().parent
if str(_plugin_dir) not in sys.path:
    sys.path.insert(0, str(_plugin_dir))

from detector import scan


def register(ctx):
    def _on_pre_llm_call(session_id: str, user_message: str, conversation_history: list,
                          is_first_turn: bool, model: str, platform: str, **kwargs):
        categories = scan(user_message or "")
        if not categories:
            return None
        listed = ", ".join(categories)
        return {
            "context": (
                "[sensitive-data-warn] The user's message looks like it may contain "
                f"{listed}. This is a heuristic guess, not a certainty -- it could be a "
                "false positive. Before continuing with the user's actual request, "
                "briefly and naturally check with them that they meant to share that "
                "(unless they've already shown clear awareness/intent), then proceed "
                "normally once they respond. Do not repeat the raw sensitive text back "
                "to them, and do not block or refuse the request."
            )
        }

    ctx.register_hook("pre_llm_call", _on_pre_llm_call)
