"""Point the printing checks at fixture firm T1016VSH1-S.

    python docs/qa/checks/printing/setup_vsh1.py

Writes ``.state/printing.json`` from accounts that already exist and uses the
Masters pass's second firm as the other firm.
"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import save_state, state  # noqa: E402

FIRM = "3c766569-d86f-4d30-acc7-d3d0775932c2"
two = state("masters")["accounts"]["admin2"]
save_state({
    "accounts": {
        "platform": {"email": "t1016vsh1.platform@fixtures.local"},
        "admin": {"email": "t1016vsh1.tradeadmin@fixtures.local", "firm_id": FIRM},
        "viewer": {"email": "t1016vsh1.viewer@fixtures.local", "firm_id": FIRM},
        "admin2": two,
    },
    "firm_id": FIRM, "firm2_id": two["firm_id"], "suffix": "t1016vsh1",
}, "printing")
print("state written")
