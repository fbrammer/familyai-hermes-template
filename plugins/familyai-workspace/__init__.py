import os
from pathlib import Path

from workspace_bootstrap import bootstrap


def register(ctx):
    def _on_session_start(session_id: str, model: str, platform: str, **kwargs):
        # The refresher normally runs this during installation; this is the
        # idempotent fallback for an already-installed adapter.
        bootstrap(Path.home(), Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / "familyai")

    ctx.register_hook("on_session_start", _on_session_start)
