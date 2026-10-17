"""Point the settings checks at fixture firm T1016VSH1-S.

    python docs/qa/checks/settings/setup_vsh1.py

Writes ``.state/settings.json`` from accounts that already exist. No firm in the
fixture set is a bare (nothing set up) firm, so the Masters pass's second firm
stands in as "bare"; checks that assume it is empty are noted in the record.
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
        "ready_admin": {"email": "t1016vsh1.tradeadmin@fixtures.local", "firm_id": FIRM},
        "viewer": {"email": "t1016vsh1.viewer@fixtures.local", "firm_id": FIRM},
        "bare_admin": two,
    },
    "ready_id": FIRM, "ready_code": "T1016VSH1-S",
    "bare_id": two["firm_id"], "bare_code": "",
    "suffix": "t1016vsh1",
}, "settings")
print("state written")
