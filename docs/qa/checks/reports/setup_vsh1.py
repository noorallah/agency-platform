"""Point the reports checks at fixture firm T1016VSH1-S.

    python docs/qa/checks/reports/setup_vsh1.py

The original setup.py copies the TEST01 accounts from the masters state; this
one names the T1016VSH1-S trade admin instead and adds a Sales executive as the seller (shared with users-roles).
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "salesmen"))
from _sm import ensure_user  # noqa: E402
from common import save_state, sign_in  # noqa: E402

FIRM = "3c766569-d86f-4d30-acc7-d3d0775932c2"
seller = "t1016vsh1.urseller@fixtures.local"
ensure_user(sign_in("t1016vsh1.platform@fixtures.local"), seller,
            "Reports check seller (t1016vsh1)", FIRM, "SALES_EXECUTIVE")
save_state({
    "accounts": {
        "admin": {"email": "t1016vsh1.tradeadmin@fixtures.local", "firm_id": FIRM},
        "platform": {"email": "t1016vsh1.platform@fixtures.local"},
        "seller": {"email": seller, "firm_id": FIRM},
    },
    "one": FIRM,
}, "reports")
print("state written")
