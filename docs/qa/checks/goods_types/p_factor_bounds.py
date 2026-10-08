"""Probe: pack-size factors of 0, negative, between one unit and itself, or with no units."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _gt import *  # noqa: F401,F403

c = Check("p_factor_bounds")
tag = suffix()
admin = client("admin")
units = uom_ids(admin)
base = {"base_uom_id": units["PIECE"], "inventory_uom_id": units["PIECE"], "purchase_uom_id": units["BOX"]}
for i, bad in enumerate(("0", "-1", "-0.5"), 1):
    status, body = prod(admin, tag, f"F{i}", **base, unit_conversion_factor=bad)
    c.eq(status, 422, f"product factor {bad} is refused 422 (got {message(body)})")
    status, body = admin.post(SETS, {"name": f"Bad {i} {tag}", "base_uom_id": units["PIECE"],
                                     "purchase_uom_id": units["BOX"], "conversion_factor": bad})
    c.eq(status, 422, f"unit-set factor {bad} is refused 422")
c.refused(prod(admin, tag, "F4", **{**base, "purchase_uom_id": units["PIECE"]}, unit_conversion_factor="6"), 422,
          "purchase unit that differs", "product factor between a unit and itself")
c.refused(prod(admin, tag, "F5", unit_conversion_factor="6"), 422, "purchase unit that differs",
          "product factor with no units at all")
c.refused(prod(admin, tag, "F6", base_uom_id=units["PIECE"], unit_conversion_factor="6"), 422,
          "purchase unit that differs", "product factor with a stock unit and no purchase unit")
c.refused(admin.post(SETS, {"name": f"Same {tag}", "base_uom_id": units["PIECE"], "purchase_uom_id": units["PIECE"],
                            "conversion_factor": "3"}), 422, "purchase unit that differs",
          "set factor between a unit and itself")
c.refused(admin.post(SETS, {"name": f"NoPur {tag}", "base_uom_id": units["PIECE"], "conversion_factor": "3"}), 422,
          "purchase unit that differs", "set factor with no purchase unit")
status, body = prod(admin, tag, "F7", **base, unit_conversion_factor="0.00000000001")
c.eq(status, 422, f"11 decimal places is refused 422, not 500 (got {status})")
status, body = prod(admin, tag, "F8", **base, unit_conversion_factor="123456789012345678901234567")
c.eq(status, 422, f"25+ digits is refused 422, not 500 (got {status})")
status, body = prod(admin, tag, "F9", **base, unit_conversion_factor="abc")
c.eq(status, 422, "text is refused 422")
status, body = prod(admin, tag, "F10", **base, unit_conversion_factor="0.5")
c.eq(status, 201, f"a fraction is accepted ({message(body)})")
status, body = prod(admin, tag, "F11", **base, unit_conversion_factor=None)
c.eq(status, 201, f"an explicit null means no rule ({message(body)})")
if status == 201:
    rows = data(admin.get(f"/api/v1/uom-framework/conversion-rules?product_id={data(body)['id']}")[1])
    c.eq(rows, [], "explicit null: no rule written")
c.done()
