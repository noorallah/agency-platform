"""Create the RCM01 test firm (SHARED, India) and bring it to can_post."""
import json, sys
sys.path.insert(0, ".")
from _rcm import sign_in

admin = sign_in()
found = admin.ok("GET", "/api/v1/firms?search=RCM01&page_size=10")
row = next((f for f in found if f.get("code") == "RCM01"), None)
if row is None:
    body = {"name": "RCM Test Firm", "code": "RCM01", "country": "IN",
            "currency_code": "INR", "financial_year_start": "2026-04-01",
            "deployment_mode": "SHARED", "notes": "Reverse charge GTA check. Test data only."}
    print(admin.call("POST", "/api/v1/firms", body)[0])
    found = admin.ok("GET", "/api/v1/firms?search=RCM01&page_size=10")
    row = next(f for f in found if f.get("code") == "RCM01")
print({k: row.get(k) for k in ("id", "code", "gst_number", "state", "state_code", "deployment_mode")})
print(sorted(row))
