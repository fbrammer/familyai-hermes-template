import os
import pathlib
import sys

_plugin_dir = pathlib.Path(__file__).resolve().parent
if str(_plugin_dir) not in sys.path:
    sys.path.insert(0, str(_plugin_dir))

from update_announcer import check_for_updates

_pending_by_session: dict[str, str] = {}


def _base_dir() -> pathlib.Path:
    hermes_home = os.environ.get("HERMES_HOME")
    root = pathlib.Path(hermes_home) if hermes_home else (pathlib.Path.home() / ".hermes")
    return root / "familyai"


def register(ctx):
    def _on_session_start(session_id: str, model: str, platform: str, **kwargs):
        message = check_for_updates(_base_dir())
        if message:
            _pending_by_session[session_id] = message

    def _on_post_llm_call(session_id: str, user_message: str, assistant_response: str,
                           conversation_history: list, model: str, platform: str, **kwargs):
        message = _pending_by_session.pop(session_id, None)
        if message:
            ctx.inject_message(message, role="system")

    ctx.register_hook("on_session_start", _on_session_start)
    ctx.register_hook("post_llm_call", _on_post_llm_call)
