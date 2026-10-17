"""Point the collections checks at fixture firm T1016VSH1-S.

    python docs/qa/checks/collections/setup_vsh1.py

Writes ``.state/collections.json`` from accounts that already exist and adds the
Cashier, Firm Manager and two Bill Collectors the checks sign in as.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _col import ensure_user  # noqa: E402
from common import save_state, sign_in, state  # noqa: E402

FIRM = "3c766569-d86f-4d30-acc7-d3d0775932c2"
STEM = "t1016vsh1"
platform = sign_in(f"{STEM}.platform@fixtures.local")
made = {}
for key, role in (("cashier", "CASHIER"), ("manager", "FIRM_MANAGER"),
                  ("collector1", "BILL_COLLECTOR"), ("collector2", "BILL_COLLECTOR")):
    email = f"{STEM}.col{key}@fixtures.local"
    made[key] = (email, ensure_user(platform, email, f"Collections {key}", FIRM, role))
two = state("buying")["accounts"]["admin2"]
save_state({
    "accounts": {
        "platform": {"email": f"{STEM}.platform@fixtures.local"},
        "admin": {"email": f"{STEM}.tradeadmin@fixtures.local", "firm_id": FIRM},
        "viewer": {"email": f"{STEM}.viewer@fixtures.local", "firm_id": FIRM},
        "admin2": two,
        **{k: {"email": e, "firm_id": FIRM} for k, (e, _) in made.items()},
    },
    "collector1_id": made["collector1"][1],
    "collector2_id": made["collector2"][1],
    "firm_id": FIRM, "firm2_id": two["firm_id"], "suffix": STEM,
}, "collections")
print("state written")
