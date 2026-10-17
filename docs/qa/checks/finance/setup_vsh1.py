"""Point the finance checks at fixture firm T1016VSH1-S.

    python docs/qa/checks/finance/setup_vsh1.py

Writes ``.state/finance.json`` from accounts that already exist and adds the
Accountant and Cashier the checks sign in as. The older ``setup.py`` runs the
``ready-firm`` fixture twice and builds new firms instead.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _fin import ensure_user  # noqa: E402
from common import save_state, sign_in, state  # noqa: E402

FIRM = "3c766569-d86f-4d30-acc7-d3d0775932c2"
STEM = "t1016vsh1"
platform = sign_in(f"{STEM}.platform@fixtures.local")
made = {}
for key, role in (("accountant", "ACCOUNTANT"), ("cashier", "CASHIER")):
    email = f"{STEM}.fin{key}@fixtures.local"
    made[key] = (email, ensure_user(platform, email, f"Finance {key}", FIRM, role))
two = state("buying")["accounts"]["admin2"]
save_state({
    "accounts": {
        "platform": {"email": f"{STEM}.platform@fixtures.local"},
        "admin": {"email": f"{STEM}.tradeadmin@fixtures.local", "firm_id": FIRM},
        "viewer": {"email": f"{STEM}.viewer@fixtures.local", "firm_id": FIRM},
        "admin2": two,
        **{k: {"email": e, "firm_id": FIRM} for k, (e, _) in made.items()},
    },
    "firm_id": FIRM, "firm2_id": two["firm_id"], "suffix": STEM,
}, "finance")
print("state written")
