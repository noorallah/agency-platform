"""Probe: a unit set's goods types and its edits (refusals and clears)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _gt import *  # noqa: F401,F403

c = Check("p_unit_set_types")
tag = suffix()
admin = client("admin")
units = uom_ids(admin)
cosm = goods_type_by_code(admin, "COSMETICS")
body_ = {"name": f"Tube set {tag}", "base_uom_id": units["TUBE"], "inventory_uom_id": units["TUBE"],
         "purchase_uom_id": units["CARTON"], "conversion_factor": "20", "goods_type_ids": [cosm["id"]]}
# A shared type the firm may not trade in is still a legitimate "suits" tie: it only orders the picker.
status, body = admin.post(SETS, body_)
c.eq(status, 201, f"tied to a shared type whether or not the firm uses it ({message(body)})")
s = data(body)
c.eq(s["goods_type_ids"], [cosm["id"]], "tie saved")


def mine():
    return next(r for r in data(admin.get(SETS)[1]) if r["id"] == s["id"])


c.refused(admin.put(f"{SETS}/{s['id']}", {"goods_type_ids": ["00000000-0000-0000-0000-000000000000"]}), 422,
          "unavailable", "update tie to an unknown type")
c.eq(admin.put(f"{SETS}/{s['id']}", {"goods_type_ids": []})[0], 200, "an empty list offers it to every product")
c.eq(mine()["goods_type_ids"], [], "ties cleared")
c.eq(admin.put(f"{SETS}/{s['id']}", {"goods_type_ids": [cosm["id"], cosm["id"]]})[0], 200,
     "a duplicated tie is collapsed, not an error")
c.refused(admin.put(f"{SETS}/{s['id']}", {"base_uom_id": None}), 422, "", "null on the base unit")
c.refused(admin.put(f"{SETS}/{s['id']}", {"name": None}), 422, "", "null on the name")
c.refused(admin.put(f"{SETS}/{s['id']}", {"conversion_factor": "0"}), 422, "", "factor 0 on update")
c.refused(admin.put(f"{SETS}/{s['id']}", {"purchase_uom_id": units["TUBE"]}), 422, "purchase unit that differs",
          "purchase unit equal to the stock unit while a factor stands")
status, body = admin.put(f"{SETS}/{s['id']}", {"purchase_uom_id": units["TUBE"], "conversion_factor": None})
c.eq(status, 200, f"clearing the factor with the units makes it consistent ({message(body)})")
c.refused(admin.put(f"{SETS}/{s['id']}", {"name": "Strip, box of 10"}), 409, "already exists",
          "a name the shared catalogue holds")
c.refused(admin.put(f"{SETS}/{s['id']}", {"name": "strip, BOX of 10  "}), 409, "already exists",
          "the same name in other case")
c.refused(admin.put(f"{SETS}/{s['id']}", {"inventory_uom_id": "00000000-0000-0000-0000-000000000000"}), 422,
          "unavailable", "an unknown unit")
c.eq(admin.put(f"{SETS}/{s['id']}", {"is_active": False})[0], 200, "retire the set")
c.ok(s["id"] not in [r["id"] for r in data(admin.get(SETS)[1])], "a retired set leaves the default list")
c.ok(s["id"] in [r["id"] for r in data(admin.get(SETS + "?include_inactive=true")[1])],
     "include_inactive brings it back")
c.eq(admin.delete(f"{SETS}/{s['id']}")[0], 204, "delete")
c.refused(admin.delete(f"{SETS}/{s['id']}"), 404, "not found", "delete twice")
c.refused(admin.put(f"{SETS}/{s['id']}", {"name": "Back"}), 404, "not found", "edit a deleted set")
c.done()
