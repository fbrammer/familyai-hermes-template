import os
import pathlib
import sys

_plugin_dir = pathlib.Path(__file__).resolve().parent
if str(_plugin_dir) not in sys.path:
    sys.path.insert(0, str(_plugin_dir))

from workspace_bootstrap import bootstrap, load_contract
from familyai_workspace import build_directive

_pending_by_session: dict[str, str] = {}


def _old_state_dir() -> pathlib.Path:
    return pathlib.Path(os.environ.get("HERMES_HOME", pathlib.Path.home() / ".hermes")) / "familyai"


def register(ctx):
    def _on_session_start(session_id: str, model: str, platform: str, **kwargs):
        # The refresher normally runs this during installation; this is the
        # idempotent fallback for an already-installed adapter.
        old_state = _old_state_dir()
        bootstrap(pathlib.Path.home(), old_state)
        contract = load_contract(old_state)
        directive = build_directive(contract)
        if directive:
            _pending_by_session[session_id] = directive

    def _on_post_llm_call(session_id: str, user_message: str, assistant_response: str,
                           conversation_history: list, model: str, platform: str, **kwargs):
        directive = _pending_by_session.pop(session_id, None)
        if directive:
            ctx.inject_message(directive, role="system")

    ctx.register_hook("on_session_start", _on_session_start)
    ctx.register_hook("post_llm_call", _on_post_llm_call)
