"""Switch boxes and pieces on for the TEST03 fixture firm and make the pack product.

    python docs/qa/checks/box_piece/setup.py

Needs ``lots/setup.py`` run first (its state holds the firm and its accounts). Turns on the
selling and buying ``box_and_piece_entry`` switches (they stay on) and makes product BP-BOX12.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _bp import Ctx, bp_admin, pack_product, switches  # noqa: E402

api = bp_admin()
switches(api, True, True)
product = pack_product(api, Ctx(api))
print("switches on; product", product["code"], product["id"])
