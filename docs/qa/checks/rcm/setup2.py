"""Register the firm for GST, open books, apply the template, activate the RCM rules."""
import sys, json
sys.path.insert(0, ".")
from _rcm import sign_in

def gstin(state, body="FXRCM1234B1Z"):
    head = state + body
    ab = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    t = 0
    for i, ch in enumerate(head):
        p = ab.index(ch) * (1 if i % 2 == 0 else 2)
        t += p // 36 + p % 36
    return head + ab[(36 - t % 36) % 36]

admin = sign_in()
row = next(f for f in admin.ok("GET", "/api/v1/firms?search=RCM01&page_size=10") if f["code"] == "RCM01")
fid = row["id"]
if not row["gst_number"]:
    g = gstin("33", "FXRCM1234B1Z")
    body = {k: row[k] for k in ("name","code","country","currency_code","financial_year_start","deployment_mode","notes","address_line1","address_line2","city","postal_code","contact_name","contact_email","contact_phone","tan_number") if row.get(k) is not None}
    body.update(gst_number=g, pan_number=g[2:12], state="Tamil Nadu")
    print(admin.call("PUT", f"/api/v1/firms/{fid}", body))
base = f"/api/v1/firms/{fid}"
r = admin.ok("GET", base + "/readiness")
steps = {s["key"]: s["status"] for s in r["steps"]}
print(steps)
for key, path, body in (("books", "/open-books", {}), ("tax", "/apply-tax-template", {}), ("branches", "/create-default-branch", None)):
    if steps.get(key) != "DONE":
        print(key, admin.call("POST", base + path, body)[0])
r = admin.ok("GET", base + "/readiness")
print({s["key"]: s["status"] for s in r["steps"]}, r["can_post"])
open("state.json", "w").write(json.dumps({"firm_id": fid}))

cur = admin.ok("GET", f"/api/v1/business-framework/firms/{fid}/profile-assignment")
rows = cur if isinstance(cur, list) else [cur]
if not any(x and x.get("business_profile_id") for x in rows):
    profs = admin.ok("GET", f"/api/v1/business-framework/firms/{fid}/profiles")
    w = next(x for x in profs if x["code"] == "WHOLESALE")
    print(admin.call("PUT", f"/api/v1/business-framework/firms/{fid}/profile-assignment", {"business_profile_id": w["id"], "is_active": True})[0])
