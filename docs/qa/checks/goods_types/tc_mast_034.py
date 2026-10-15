"""TC-MAST-034: pieces per pack on a product import becomes the item's box (L5 step 12)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _gt import *  # noqa: F401,F403

c = Check("tc_mast_034")
tag = suffix()
admin = client("admin")
units = uom_ids(admin)
med = ensure_use(admin, "MEDICINE")
tablets = cat(admin, tag, "TABLETS", goods_type_id=med["id"])


def code(name):
    return f"{tag}-{name}"


def by_code(c_):
    rows = [r for r in data(admin.get(f"{PRODUCTS}?search={c_}&page_size=20")[1]) if r["code"] == c_]
    return rows[0] if rows else None


def rule_of(product_id):
    rows = data(admin.get(f"/api/v1/uom-framework/conversion-rules?product_id={product_id}&page_size=50")[1])
    return [(r["from_uom_id"], r["to_uom_id"], float(r["conversion_factor"])) for r in rows]


# The template names the two columns.
status, raw = admin.raw(f"{PRODUCTS}/import-template?format=csv")
heading = raw.decode("utf-8").splitlines()[0] if isinstance(raw, bytes) else str(raw).splitlines()[0]
c.ok("PiecesPerPack" in heading and "PackUnit" in heading, "template has PiecesPerPack and PackUnit", heading)

status, body = prod(admin, tag, "PP-OLD", category_id=tablets["id"], base_uom_id=units["PIECE"],
                    inventory_uom_id=units["PIECE"], purchase_uom_id=units["PIECE"])
c.eq(status, 201, f"PP-OLD created ({message(body)})")

# The old program's heading, "Pieces per case", is read as PiecesPerPack.
cols = ["Code", "Name", "Category", "Unit", "UnitSet", "Pieces per case", "PackUnit"]
r = lambda n, unit="", per="", box="", uset="": {"Code": code(n), "Name": n, "Category": tablets["code"], "Unit": unit,  # noqa: E731
                                                  "UnitSet": uset, "Pieces per case": per, "PackUnit": box}
bad = [r("PP-1", "", "12"), r("PP-9", "PIECE", "2.5"), r("PP-8", "PIECE", "12", "CRATEX"), r("PP-7", "PIECE", "12", "PIECE")]
status, body = import_file(admin, csv_bytes(bad, cols))
rep = data(body)
c.eq([(i["code"], i["column"]) for i in rep.get("issues", [])],
     [(code("PP-9"), "PiecesPerPack"), (code("PP-8"), "PackUnit"), (code("PP-7"), "PackUnit")], "three problems by column")
c.ok("PiecesPerPack" in rep.get("columns_used", []), "Pieces per case is read as PiecesPerPack", rep.get("columns_used"))

good = [r("PP-1", "", "12"), r("PP-2", "STRIP", "10", "CASE"), r("PP-3", "PIECE", "1"),
        r("PP-4", "", "6", "", "Strip, box of 10"), r("PP-OLD", "", "24"), r("PP-5", "PIECE", "", "BOX")]
status, body = import_file(admin, csv_bytes(good, cols), existing="update")
rep = data(body)
c.eq(rep.get("issues"), [], "the good file has no problems")
c.eq(sorted((w["code"], w["column"]) for w in rep.get("warnings", [])),
     sorted([(code("PP-4"), "PiecesPerPack"), (code("PP-OLD"), "PiecesPerPack"), (code("PP-5"), "PackUnit")]),
     "three passed-over warnings")
c.ok(all("is passed over" in w["message"] for w in rep.get("warnings", [])), "each warning says passed over", issues_text(body))
status, body = import_file(admin, csv_bytes(good, cols), apply=True, existing="update")
c.eq(data(body).get("imported"), True, f"imports ({issues_text(body)})")

p1, p2, p3, p4, old = (by_code(code(n)) for n in ("PP-1", "PP-2", "PP-3", "PP-4", "PP-OLD"))
if p1:
    c.eq((p1["base_uom_id"], p1["inventory_uom_id"], p1["sales_uom_id"], p1["purchase_uom_id"]),
         (units["PIECE"], units["PIECE"], units["PIECE"], units["BOX"]), "PP-1 in pieces, bought in boxes")
    c.eq(rule_of(p1["id"]), [(units["BOX"], units["PIECE"], 12.0)], "PP-1 own rule 1 Box = 12 Piece")
    full = data(admin.get(f"{PRODUCTS}/{p1['id']}")[1])
    c.eq((full.get("pack_size") and float(full["pack_size"]), full.get("pack_unit_code")), (12.0, "BOX"), "PP-1 answers its selling pack")
    c.eq((full.get("buying_pack_size") and float(full["buying_pack_size"]), full.get("buying_pack_unit_code")), (12.0, "BOX"), "PP-1 answers its buying pack")
if p2:
    c.eq(rule_of(p2["id"]), [(units["CASE"], units["STRIP"], 10.0)], "PP-2 own rule 1 Case = 10 Strip")
if p3:
    c.eq((p3["purchase_uom_id"], rule_of(p3["id"])), (units["PIECE"], []), "PP-3 (one per pack) pieces only")
if p4:
    c.eq(rule_of(p4["id"]), [(units["BOX"], units["STRIP"], 10.0)], "PP-4 takes the unit set's 10, not the row's 6")
if old:
    c.eq((old["purchase_uom_id"], rule_of(old["id"])), (units["PIECE"], []), "PP-OLD keeps its units and gains no rule")
c.done()
