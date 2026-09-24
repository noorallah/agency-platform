"""Write every seeded role's permission codes to roles.json (step 1 of 3).

Run from backend/:  .venv\Scripts\python.exe ..\docs\qa\tools\export_roles.py <out dir>
"""

import json
import sys
from pathlib import Path

import app.identity.system_seed as seed

out = Path(sys.argv[1])
json.dump(
    {
        "roles": {r: sorted(c) for r, c in seed.ROLE_PERMISSION_CODES.items()},
        "firm_roles": sorted(seed.FIRM_ROLE_CODES),
    },
    open(out / "roles.json", "w", encoding="utf-8"),
    indent=1,
)
print("wrote", out / "roles.json")
