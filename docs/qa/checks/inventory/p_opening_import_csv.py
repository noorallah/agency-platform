"""Probe (round 9): opening stock sent as a CSV file; a row that cannot be read is refused by name and writes nothing (D-STK-58).

`POST /inventory/opening-stock/import` with `format=csv` (no screen calls it; the screen's import is `import-file`)."""
from _inv import *
from _flow import *

c = Check("p_opening_import_csv")
w = World()
wh = w.warehouse()["id"]
p1, p2 = w.product(), w.product()
IMP = f"{INV}/opening-stock/import"


def send(reference: str, text: str | bytes, fmt: str = "csv", **over: str) -> tuple[int, Any]:
    """Upload one opening-stock file with the form fields the route asks for."""
    fields = {"format": fmt, "reference_number": reference, "posting_date": w.today, "branch_id": w.branch_id,
              "warehouse_id": wh, "auto_post": "true", **over}
    content = text if isinstance(text, bytes) else text.encode()
    return w.admin.upload(IMP, f"os.{fmt}", content, fields=fields)


def documents(reference: str) -> list[dict[str, Any]]:
    """The firm's opening-stock documents carrying this number."""
    st, b = w.admin.get(f"{INV}/opening-stock?search={reference}&page_size=50")
    return [r for r in data(b) if r["reference_number"] == reference] if st == 200 else []


ref = f"OSC-{w.tag}"
HEAD = "ProductId,Quantity\n"
# a good file
st, b = send(f"{ref}-A", HEAD + f"{p1['id']},10\n")
c.ok(st in (200, 201) and data(b)["status"] == "POSTED", "a good file is saved and posted", (st, message(b)[:200]))
c.eq(w.qty(p1["id"], wh), D(10), "ten on the shelf")
# rows that cannot be read: each a 422 that says which row, and nothing written
bad = {
    "a product id that is not an id": HEAD + f"{p2['id']},4\nnot-an-id,3\n",
    "a quantity that is not a number": HEAD + f"{p2['id']},4\n{p2['id']},lots\n",
    "a quantity below nought": HEAD + f"{p2['id']},-4\n",
    "a level that is not a number": "ProductId,Quantity,ReorderLevel\n" + f"{p2['id']},4,few\n",
    "a location that is not an id": "ProductId,Quantity,StorageNodeId\n" + f"{p2['id']},4,shelf\n",
}
for n, (what, text) in enumerate(bad.items()):
    number = f"{ref}-B{n}"
    st, b = send(number, text)
    c.ok(st == 422, f"{what} is refused as a 422", (st, message(b)[:200]))
    c.eq(len(documents(number)), 0, f"{what}: no document is left")
c.eq(w.qty(p2["id"], wh), D(0), "nothing of the second product arrived")
st, b = send(f"{ref}-C", b"\xff\xfe\x00bad", fmt="csv")
c.ok(st == 422, "a file that is not text is refused as a 422", (st, message(b)[:200]))
st, b = send(f"{ref}-D", b"this is not a workbook", fmt="xlsx")
c.ok(st == 422, "a file that is not a workbook is refused as a 422", (st, message(b)[:200]))
st, b = send(f"{ref}-E", HEAD, fmt="csv")
c.ok(st == 422, "a file with no rows is refused", (st, message(b)[:200]))
c.eq(len(documents(f"{ref}-E")), 0, "and leaves no document")
st, b = send(f"{ref}-F", HEAD + f"{p2['id']},4\n", posting_date="tomorrow")
c.ok(st == 422, "a posting date that is not a date is refused", (st, message(b)[:200]))
# the corrected file goes in
st, b = send(f"{ref}-B0", HEAD + f"{p2['id']},4\n")
c.ok(st in (200, 201) and data(b)["status"] == "POSTED", "the corrected file goes in under a refused number", (st, message(b)[:200]))
c.eq(w.qty(p2["id"], wh), D(4), "four of the second product arrive")
c.done()
