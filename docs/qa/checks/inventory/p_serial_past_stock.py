"""Probe: Add Serial numbers only a unit the firm holds (D-STK-50)."""
from _inv import *

c = Check("p_serial_past_stock")
w = World()
S = "/api/v1/batch-serial/serials"
a, b = w.warehouse("A"), w.warehouse("B")
ps = w.product("S", goods_type="ELECTRONICS")


def add(number: str, **where: str) -> tuple[int, object]:
    """Add one serial number by hand, naming a warehouse or none."""
    return w.admin.post(S, {"product_id": ps["id"], "serial_number": f"{number}{w.tag}", **where})


def on_hand() -> int:
    """How many units of the product carry a number and are on hand."""
    return len([x for x in all_rows(w.admin, f"{S}?product_id={ps['id']}")
                if x["product_id"] == ps["id"] and x["status"] in ("AVAILABLE", "RESERVED", "DAMAGED")])


# nothing held: no number, with a warehouse or without
c.refused(add("N0", warehouse_id=a["id"]), 422, "holds 0", "nothing in the warehouse: a number is refused")
c.refused(add("N0"), 422, "The firm holds 0", "nothing in the firm: a number naming no warehouse is refused")
c.eq(on_hand(), 0, "no unit was numbered")

# two units brought in as a quantity (an opening line with no numbers posts as one)
w.stock_in(a["id"], ps["id"], 2)
c.eq(add("N1", warehouse_id=a["id"])[0], 201, "two held: the first number")
c.eq(add("N2", warehouse_id=a["id"])[0], 201, "two held: the second number")
third = add("N3", warehouse_id=a["id"])
c.refused(third, 422, "holds 2", "two held and two numbered: the third is refused")
c.ok("2 are already numbered" in message(third[1]), "the refusal says how many are numbered", message(third[1]))
c.refused(add("N3"), 422, "The firm holds 2", "and refused for the firm as a whole")
c.eq(on_hand(), 2, "two units numbered, no more")

# one more unit in another warehouse: the first warehouse is still full, the firm is not
w.stock_in(b["id"], ps["id"], 1)
c.refused(add("N3", warehouse_id=a["id"]), 422, "holds 2", "a unit in B does not make room in A")
c.eq(add("N3", warehouse_id=b["id"])[0], 201, "the unit in B takes its number")
c.refused(add("N4"), 422, "The firm holds 3", "three held and three numbered: the firm is full")

# a unit that is no longer on hand is a record of the past and is not counted
first = next(x for x in all_rows(w.admin, f"{S}?product_id={ps['id']}") if x["serial_number"] == f"N1{w.tag}")
c.eq(w.admin.put(f"{S}/{first['id']}", {"status": "SCRAPPED"})[0], 200, "one number scrapped")
c.eq(add("N5", warehouse_id=a["id"])[0], 201, "the unit it stood for takes a new number")
c.refused(w.admin.put(f"{S}/{first['id']}", {"status": "AVAILABLE"}), 422, "holds 2",
          "the scrapped number cannot come back past the stock")
c.eq(on_hand(), 3, "three units numbered against three held")
c.done()
