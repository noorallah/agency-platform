"""TC-MAST-032: a pack's own code finds its product, and says what a pack holds.

Makes two products and their packs under a fresh suffix on TEST01, so it runs
alone and runs twice. Leaves them behind: a pack's code must stay unique, and
each run's codes carry its own suffix.
"""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from decimal import Decimal

from common import Check, client, data, message, suffix

import _gt

c = Check("tc_mast_032")
admin, manager, sales, store = (
    client("admin"), client("manager"), client("sales"), client("store"))
other_firm = client("test02_admin")
tag = f"PK{suffix()}".upper()
LOOKUP = "/api/v1/uom-framework/barcode-lookup?code="
OWN, CARTON, CARTON_EAN, SHARED = (
    f"{tag}-OWN", f"{tag}-CTN", f"{tag}-EAN", f"{tag}-BOTH")


def made(answer: tuple, what: str) -> dict:
    """Return what a create answered, or stop the case."""
    status, body = answer
    if status not in (200, 201):
        raise SystemExit(f"PRECONDITION {what}: {status} {message(body)}")
    return data(body)


def levels(product_id: str) -> str:
    """Return the path of a product's packaging levels."""
    return f"/api/v1/uom-framework/products/{product_id}/packaging-levels"


def found(api, text: str) -> list[dict]:
    """Return the product rows a list search answers."""
    status, body = api.get(f"/api/v1/products?search={text}&page_size=25")
    if status != 200:
        raise SystemExit(f"PRECONDITION product search {text}: {status} {message(body)}")
    return data(body)


units = _gt.uom_ids(admin)
box = units.get("BOX") or units.get("CARTON") or next(iter(units.values()))
box_code = next(code for code, uom_id in units.items() if uom_id == box)
soap = made(_gt.prod(admin, tag, "SOAP", barcode=OWN), "the product with a pack")
tea = made(_gt.prod(admin, tag, "TEA"), "the product without one")
carton = made(admin.post(levels(soap["id"]), {
    "level_name": "Carton", "uom_id": box, "conversion_to_base_factor": "24",
    "barcode": CARTON, "ean": CARTON_EAN,
}), "the carton")

# (a) the pack's code answers with the product and what one pack holds
s, b = admin.get(LOOKUP + CARTON)
hit = data(b) if s == 200 else {}
c.eq(s, 200, "(a) the carton's barcode is found")
c.eq(hit.get("product_id"), soap["id"], "(a) it is the carton's product")
c.eq(hit.get("packaging_level_id"), carton["id"], "(a) it names the level")
c.eq(hit.get("level_name"), "Carton", "(a) the level's name")
c.eq(Decimal(str(hit.get("base_quantity", 0))), Decimal(24), "(a) one scan is 24")
c.eq(hit.get("matched_field"), "barcode", "(a) found as a barcode")
c.eq(hit.get("uom_code"), box_code, "(a) the pack's unit is named")
c.ok("stock_uom_code" in hit, "(a) the product's stock unit is answered", hit)
s, b = admin.get(LOOKUP + CARTON_EAN)
c.eq((s, data(b).get("matched_field") if s == 200 else None), (200, "ean"),
     "(a) the same pack by its EAN")

# (b) the product's own barcode is one
s, b = admin.get(LOOKUP + OWN)
hit = data(b) if s == 200 else {}
c.eq((s, hit.get("product_id")), (200, soap["id"]), "(b) the product's own barcode")
c.eq(hit.get("packaging_level_id"), None, "(b) no level for the product's own code")
c.eq(hit.get("uom_code"), None, "(b) no pack unit for the product's own code")
c.eq(Decimal(str(hit.get("base_quantity", 0))), Decimal(1), "(b) one scan is one")

# (c) every search box fed by the product list finds the product by its pack
for label, code in (("barcode", CARTON), ("EAN", CARTON_EAN), ("part of it", CARTON[2:])):
    rows = found(admin, code)
    c.eq([row["id"] for row in rows], [soap["id"]],
         f"(c) a product search for the pack's {label} answers its product alone")
rows = found(admin, tag)
by_id = {row["id"]: row for row in rows}
c.eq(by_id.get(soap["id"], {}).get("pack_codes"), [CARTON, CARTON_EAN],
     "(c) the row carries the codes of its packs")
c.eq(by_id.get(tea["id"], {}).get("pack_codes"), [],
     "(c) a product with no pack carries none")
c.eq(_gt.get_product(admin, soap["id"]).get("pack_codes"), [CARTON, CARTON_EAN],
     "(c) the product read alone carries them too")
c.eq(found(admin, f"{tag}-NOSUCH"), [], "(c) a code nothing carries finds nothing")

# (d) who may scan: every role that reads units; who may record a pack
for label, api in (("manager", manager), ("sales manager", sales), ("store", store)):
    s, b = api.get(LOOKUP + CARTON)
    c.eq((s, data(b).get("product_id") if s == 200 else message(b)),
         (200, soap["id"]), f"(d) the {label} may scan the carton")
    c.eq([row["id"] for row in found(api, CARTON)], [soap["id"]],
         f"(d) the {label}'s product search finds it by the pack")
c.refused(sales.post(levels(tea["id"]), {
    "level_name": "Box", "conversion_to_base_factor": "10", "barcode": f"{tag}-X",
}), 403, "", "(d) a sales manager may not record a pack")

# (e) refusals: nothing carries it; another firm's code; two things carry it
c.refused(admin.get(LOOKUP + f"{tag}-NOSUCH"), 404, f"{tag}-NOSUCH",
          "(e) a code nothing carries is refused by name")
c.refused(other_firm.get(LOOKUP + CARTON), 404, CARTON,
          "(e) another firm's pack is not found")
c.eq(found(other_firm, CARTON), [], "(e) nor does that firm's product search find it")
made(admin.post(levels(soap["id"]), {
    "level_name": "Pallet", "conversion_to_base_factor": "480", "upc": SHARED,
}), "a second level on the first product")
second = admin.post(levels(tea["id"]), {
    "level_name": "Box", "conversion_to_base_factor": "10", "barcode": SHARED,
})
if second[0] in (200, 201):
    c.refused(admin.get(LOOKUP + SHARED), 409, "carry the code",
              "(e) a code two packs carry is refused, not guessed at")
    c.eq(sorted(row["id"] for row in found(admin, SHARED)),
         sorted([soap["id"], tea["id"]]),
         "(e) the product search shows both, so somebody can put it right")
else:
    c.ok(second[0] in (409, 422), "(e) a code a pack already carries is refused at the save",
         (second[0], message(second[1])))

# (f) a pack taken off the product stops answering
s, _b = admin.delete(f"{levels(soap['id'])}/{carton['id']}")
c.ok(s in (200, 204), "(f) the carton is deleted", s)
c.refused(admin.get(LOOKUP + CARTON), 404, CARTON, "(f) its code is no longer found")
c.eq(found(admin, CARTON), [], "(f) nor by the product search")
c.done()
