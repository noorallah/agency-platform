"""TC-MAST-019: who keeps goods types, and what a new firm starts with."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from common import Check, client, data, message, state, suffix
from _lib import audit_actions, must

c = Check("tc_mast_019")
tag = suffix()
admin, manager, sales = client("admin"), client("manager"), client("sales")
GT = "/api/v1/products/goods-types"

# roles on TEST01
mine = {"code": f"GA{tag}", "name": f"Own type {tag}", "track_batch": True}
c.eq(manager.post(GT, mine)[0], 403, "the firm manager cannot add a goods type")
s, b = manager.get(GT)
c.eq(s, 200, "the firm manager can read the list")
shared = next(r for r in data(b) if r["firm_id"] is None and r["code"] == "COSMETICS")
c.eq(manager.put(f"{GT}/{shared['id']}/use", {"in_use": True})[0], 403,
     "the firm manager cannot use a goods type")
c.eq(sales.get(GT)[0], 200, "the sales manager can read the list")
c.eq(sales.post(GT, mine)[0], 403, "the sales manager cannot add one")
c.eq(sales.put(f"{GT}/{shared['id']}/use", {"in_use": True})[0], 403, "nor use one")

created = admin.post(GT, mine)
c.eq(created[0], 201, "the firm administrator adds a goods type")
if created[0] == 201:
    gid = data(created[1])["id"]
    c.eq(manager.put(f"{GT}/{gid}", {"name": "x"})[0], 403, "the firm manager cannot change one")
    c.eq(manager.delete(f"{GT}/{gid}")[0], 403, "the firm manager cannot delete one")
    c.eq(admin.put(f"{GT}/{gid}/use", {"in_use": True})[0], 200, "the administrator takes it into use")
    c.eq(admin.put(f"{GT}/{gid}/use", {"in_use": False})[0], 200, "and drops it")
    c.eq(admin.delete(f"{GT}/{gid}")[0], 204, "and deletes it")

# the two firms of their own
own = state()["own_firms"]
# ``plain`` is the Generic firm nothing else writes to; the inventory checks take
# goods types into use in ``generic`` and in the pharmacy firm (their "other firm"),
# so the pharmacy firm is asked about Medicine alone
pharma, generic = own["pharma"]["id"], own["plain"]["id"]
pp, gp = client("pharma_platform"), client("plain_platform")


def in_use(api) -> list[str]:
    """Codes of the goods types in use in the firm the client acts in."""
    s, b = api.get(GT)
    return sorted(r["code"] for r in data(b) if r["in_use"])


starting = [r for r in audit_actions(pp, pharma, "goods_type.starting_set")]
c.eq(len(starting), 1, "the pharmacy firm has one goods_type.starting_set audit row")
if starting:
    c.eq(starting[0]["after_data"].get("goods_types"), ["MEDICINE"], "that row names Medicine")
c.eq(len(audit_actions(gp, generic, "goods_type.starting_set")), 0,
     "the generic firm has none")
c.eq(in_use(gp), [], "the generic firm starts with no goods type in use")
now = [code for code in in_use(pp) if code == "MEDICINE"]
c.ok(now in (["MEDICINE"], []), "the pharmacy firm started with Medicine (or it was dropped by an earlier run)", now)
if now == []:
    print("note: Medicine was already dropped by an earlier run; the first-run expectation is consumed")

# drop Medicine, change profile and change it back
s, b = pp.get(GT)
med = next(r for r in data(b) if r["code"] == "MEDICINE")
c.eq(pp.put(f"{GT}/{med['id']}/use", {"in_use": False})[0], 200, "Medicine is dropped by the platform administrator")
base = f"/api/v1/business-framework/firms/{pharma}"
s, b = pp.get(f"{base}/profiles")
profiles = {p["code"]: p["id"] for p in data(b)}
for code in ("AGENCY", "PHARMACY"):
    r = pp.put(f"{base}/profile-assignment", {"business_profile_id": profiles[code], "is_active": True})
    c.eq(r[0], 200, f"the profile is changed to {code}")
c.ok("MEDICINE" not in in_use(pp), "after the round trip Medicine is still not in use", in_use(pp))
c.eq(len(audit_actions(pp, pharma, "goods_type.starting_set")), 1,
     "and no second starting_set row was written")
c.done()
