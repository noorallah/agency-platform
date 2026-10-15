"""TC-TERR-007: a salesman with no sign-in covers a round; a user's id does not."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sm import *

c = Check("tc_terr_007")
a = admin()
held = state()
tag = suffix(5)
phone = must(a.post(SM, {"name": f"Phone order {tag}"}), "entry")
route = make_route(a, tag, [])
status, body = a.put(f"{T}/{route['id']}/salesmen", {"assignments": [{"salesman_id": phone["id"], "is_primary": False}]})
c.eq(status, 200, f"the assignment is accepted ({message(body)[:150]})")
status, body = a.get(f"{T}/coverage/salesmen")
rows = data(body) if status == 200 else []
mine = [r for r in rows if r.get("salesman_id") == phone["id"]]
c.ok(bool(mine), "Coverage lists the entry", rows)
if mine:
    c.ok(mine[0].get("assigned_routes", 0) >= 1, "against the round", mine[0])
status, body = a.get(f"{T}/{route['id']}/salesmen")
c.ok(status == 200 and phone["id"] in str(body), "the round reads the entry back", body)

exec_uid = user_id_of(held["accounts"]["exec"]["email"])
c.refused(
    a.put(f"{T}/{route['id']}/salesmen", {"assignments": [{"salesman_id": exec_uid, "is_primary": False}]}),
    422, "not on this firm's list of salesmen", "an assignment naming a user's id",
)
c.done()
