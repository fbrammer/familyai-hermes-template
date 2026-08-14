"""No hooks of its own -- scope_filter is imported directly by
escalation-support (family side) and the support agent (ubuntu2026 side)
so both legs of the relay run the identical check."""

import pathlib
import sys

_plugin_dir = pathlib.Path(__file__).resolve().parent
if str(_plugin_dir) not in sys.path:
    sys.path.insert(0, str(_plugin_dir))


def register(ctx):
    # Intentionally no hooks registered here -- see module docstring.
    pass
