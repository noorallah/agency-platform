"""Copy the masters accounts (TEST01) into the reports state; no fixture run."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from common import save_state, state  # noqa: E402

held = state("masters")
save_state({"accounts": held["accounts"], "one": held.get("one", {})}, "reports")
print("reports state written from masters accounts")
