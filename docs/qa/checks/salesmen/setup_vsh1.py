"""Point the salesmen and territory checks at fixture firm T1016VSH1-S.

    python docs/qa/checks/salesmen/setup_vsh1.py

Writes ``.state/salesmen.json`` from accounts that already exist, adds the one
Sales executive the checks need, and uses the Masters pass's second firm.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _sm import ensure_user  # noqa: E402
from common import save_state, sign_in, state  # noqa: E402

FIRM = "3c766569-d86f-4d30-acc7-d3d0775932c2"
platform = sign_in("t1016vsh1.platform@fixtures.local")
execu = "t1016vsh1.smexec@fixtures.local"
ensure_user(platform, execu, "Salesman check executive (t1016vsh1)", FIRM, "SALES_EXECUTIVE")
two = state("masters")["accounts"]["admin2"]
save_state({
    "accounts": {
        "platform": {"email": "t1016vsh1.platform@fixtures.local"},
        "admin": {"email": "t1016vsh1.tradeadmin@fixtures.local", "firm_id": FIRM},
        "viewer": {"email": "t1016vsh1.viewer@fixtures.local", "firm_id": FIRM},
        "exec": {"email": execu, "firm_id": FIRM},
        "admin2": two,
    },
    "firm_id": FIRM, "firm2_id": two["firm_id"], "suffix": "t1016vsh1",
}, "salesmen")
print("state written")
