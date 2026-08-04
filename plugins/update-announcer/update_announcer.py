import pathlib
from typing import Optional

from update_queue import read_pending, clear_pending, compose_digest, load_prefs, save_prefs

OPT_OUT_SENTENCE = "\n\n(You can ask me to stop telling you about updates like this any time.)"


def check_for_updates(base_dir: pathlib.Path) -> Optional[str]:
    entries = read_pending(base_dir)
    if not entries:
        return None

    prefs = load_prefs(base_dir)
    message = None

    if prefs["enabled"]:
        message = compose_digest(entries)
        if not prefs["ever_delivered"]:
            message += OPT_OUT_SENTENCE
            prefs["ever_delivered"] = True
            save_prefs(base_dir, prefs)

    clear_pending(base_dir)
    return message
