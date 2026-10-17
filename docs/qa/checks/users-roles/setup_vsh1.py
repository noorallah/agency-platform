"""Point the users-roles checks at fixture firm T1016VSH1-S.

    python docs/qa/checks/users-roles/setup_vsh1.py

The original setup.py runs fixtures that create new firms, so it is not run.
Firm ``one`` is T1016VSH1-S (admin = its trade admin), firm ``two`` is the
Masters pass's second firm. Adds one Sales executive as the "seller".
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "salesmen"))
from _sm import ensure_user  # noqa: E402
from common import save_state, sign_in, state  # noqa: E402

FIRM = "3c766569-d86f-4d30-acc7-d3d0775932c2"
platform = sign_in("t1016vsh1.platform@fixtures.local")
seller = "t1016vsh1.urseller@fixtures.local"
ensure_user(platform, seller, "Users-roles check seller (t1016vsh1)", FIRM, "SALES_EXECUTIVE")
two = state("masters")["accounts"]["admin2"]
save_state({
    "accounts": {
        "admin": {"email": "t1016vsh1.tradeadmin@fixtures.local", "firm_id": FIRM},
        "platform": {"email": "t1016vsh1.platform@fixtures.local"},
        "seller": {"email": seller, "firm_id": FIRM},
    },
    "one": FIRM,
    "two": two["firm_id"],
}, "users-roles")
print("state written")
