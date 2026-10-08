"""Probe: another firm's goods type is invisible and unusable by id."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _gt import *  # noqa: F401,F403

c = Check("p_cross_firm")
tag = suffix()
admin = client("admin")
other = client("platform").inside(firm_ids()["TEST02"])
units = uom_ids(admin)
status, body = other.post(GT, {"code": f"{tag}-X", "name": f"Other firm {tag}"})
if not c.eq(status, 201, f"a type is made in the second firm ({message(body)})"):
    c.done()
foreign = data(body)
c.ok(foreign["id"] not in [r["id"] for r in data(admin.get(GT)[1])], "the first firm's list does not hold it")
c.refused(admin.put(f"{GT}/{foreign['id']}", {"name": "Taken"}), 404, "not found", "PUT by id")
c.refused(admin.put(f"{GT}/{foreign['id']}/use", {"in_use": True}), 404, "not found", "use by id")
c.refused(admin.delete(f"{GT}/{foreign['id']}"), 404, "not found", "DELETE by id")
c.refused(make_category(admin, tag, "FOREIGN", goods_type_id=foreign["id"]), 422, "unavailable", "category carrying it")
c.refused(admin.post(SETS, {"name": f"Foreign set {tag}", "base_uom_id": units["PIECE"], "goods_type_ids": [foreign["id"]]}),
          422, "unavailable", "unit set tied to it")
# The same code in two firms is fine.
status, body = admin.post(GT, {"code": f"{tag}-X", "name": f"Same code {tag}"})
c.eq(status, 201, f"the same code can be used by the first firm ({message(body)})")
# And the reverse: the second firm cannot reach the first firm's.
mine = data(body)
c.refused(other.put(f"{GT}/{mine['id']}", {"name": "Taken"}), 404, "not found", "reverse PUT by id")
other.delete(f"{GT}/{foreign['id']}")
admin.delete(f"{GT}/{mine['id']}")
c.done()
