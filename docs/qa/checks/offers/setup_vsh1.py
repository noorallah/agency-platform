"""Point the offers checks at fixture firm T1016VSH1-S.

    python docs/qa/checks/offers/setup_vsh1.py

Writes ``.state/offers.json`` from accounts that already exist and adds the
Sales executive ("clerk") and the custom no-choice role user ("nochoose").
The older ``setup.py`` builds a new selling-firm fixture instead.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _offer import ensure_user  # noqa: E402
from common import save_state, sign_in  # noqa: E402
from setup import no_choose_role  # noqa: E402

FIRM = "3c766569-d86f-4d30-acc7-d3d0775932c2"
STEM = "t1016vsh1"
platform_email = f"{STEM}.platform@fixtures.local"
admin_email = f"{STEM}.tradeadmin@fixtures.local"
platform = sign_in(platform_email)
role_code = f"ofr-no-choose-{STEM}"
no_choose_role(sign_in(admin_email, firm_id=FIRM), role_code)
accounts = {
    "platform": {"email": platform_email},
    "admin": {"email": admin_email, "firm_id": FIRM},
}
for handle, role, title in (
    ("clerk", "SALES_EXECUTIVE", "Offer clerk"),
    ("nochoose", role_code, "Offer clerk without the choice"),
):
    email = f"{STEM}.ofr{handle}@fixtures.local"
    ensure_user(platform, email, f"{title} ({STEM})", FIRM, role)
    accounts[handle] = {"email": email, "firm_id": FIRM, "role": role}
save_state({"accounts": accounts, "firm_id": FIRM, "firm_code": "T1016VSH1-S",
            "suffix": STEM}, "offers")
print("state written")
