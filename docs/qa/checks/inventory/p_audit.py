"""Probe: every stock write leaves an audit row in the firm's own trail, naming the actor; a refused write leaves none."""
from datetime import date, timedelta

from _inv import *
from _flow import *

c = Check("p_audit")
w = World()
me = data(w.admin.get("/api/v1/me")[1])["id"]
a, b2 = w.warehouse("A"), w.warehouse("B")
p = w.product()
pb = w.product(goods_type="MEDICINE")
w.stock_in(a["id"], p["id"], 30)
# Round 4's rules: a batch-tracked product is produced into a named batch (D-STK-53), a batch of goods that
# expire carries its date (D-STK-48), and a serial number is added only for a unit the firm holds (D-STK-50).
later = (date.fromisoformat(w.today) + timedelta(days=400)).isoformat()
# One unit held whose number was scrapped is the unit a new number may be added for.
ps = w.product("S", goods_type="ELECTRONICS")
c.eq(receive(w, a["id"], ps["id"], 1, serials=[f"OLD{w.tag}"])["status"][0], 200, "one numbered unit received")
old = all_rows(w.admin, f"/api/v1/batch-serial/serials?product_id={ps['id']}")[0]
c.eq(w.admin.put(f"/api/v1/batch-serial/serials/{old['id']}", {"status": "SCRAPPED"})[0], 200, "its number scrapped")
base = {"branch_id": w.branch_id, "product_id": p["id"], "transaction_date": w.today, "warehouse_id": a["id"]}


tbase = {k: v for k, v in base.items() if k != "warehouse_id"}


def total() -> int:
    """Rows in the firm's trail."""
    return int(w.admin.get("/api/v1/audit-logs?page=1&page_size=1")[1]["pagination"]["total_records"])


def audited(label: str, send, prefix: str) -> None:  # noqa: ANN001
    """Run a write and look at the new audit rows."""
    before = total()
    st, b = send()
    after = total()
    if not c.ok(st < 300, f"{label}: the write itself succeeded", (st, message(b))):
        return
    new = after - before
    if not c.ok(new >= 1, f"{label}: left an audit row", new):
        return
    rows = data(w.admin.get(f"/api/v1/audit-logs?page=1&page_size={min(new, 100)}")[1])
    c.ok(any(r["action"].startswith(prefix) for r in rows), f"{label}: an action starting {prefix}", [r["action"] for r in rows])
    c.ok(any(r["actor_id"] == me for r in rows if r["action"].startswith(prefix)), f"{label}: the audit names the actor")


audited("adjustment", lambda: w.admin.post(f"{INV}/adjustments", {**base, "quantity": "-1", "reference_number": f"A{w.tag}", "reason_code": "LOSS"}), "inventory.")
audited("write-off", lambda: w.admin.post(f"{INV}/write-offs", {**base, "quantity": "1", "reason": "DAMAGE", "reference_number": f"W{w.tag}"}), "inventory.")
audited("transfer", lambda: w.admin.post(f"{INV}/transfers", {**tbase, "from_warehouse_id": a["id"], "to_warehouse_id": b2["id"], "quantity": "1", "reference_number": f"T{w.tag}"}), "inventory.")
audited("quarantine", lambda: w.admin.post(f"{INV}/quarantine", {**base, "action": "HOLD", "quantity": "1", "reference_number": f"Q{w.tag}"}), "inventory.")
audited("opening stock", lambda: w.admin.post(f"{INV}/opening-stock", {"branch_id": w.branch_id, "warehouse_id": b2["id"], "reference_number": f"O{w.tag}", "posting_date": w.today,
                                                                      "lines": [{"product_id": p["id"], "quantity": "1", "unit_cost": "5"}]}), "opening_stock.")
trf = {}
made: dict = {}


def keep(key: str, answer: tuple[int, object]) -> tuple[int, object]:
    """Remember the record a create answered with."""
    if answer[0] < 300:
        made[key] = data(answer[1])
    return answer


audited("stock transfer create", lambda: keep("trf", w.admin.post(f"{INV}/stock-transfers", {"transfer_date": w.today, "from_warehouse_id": a["id"], "to_warehouse_id": b2["id"], "lines": [{"product_id": p["id"], "quantity": "2"}]})), "")
t = made["trf"]
audited("stock transfer dispatch", lambda: w.admin.post(f"{INV}/stock-transfers/{t['id']}/dispatch", {}), "")
audited("stock transfer receive", lambda: w.admin.post(f"{INV}/stock-transfers/{t['id']}/receive", {"lines": [{"line_number": 1, "received_quantity": "2"}]}), "")
audited("count open", lambda: keep("cnt", w.admin.post(f"{INV}/counts", {"branch_id": w.branch_id, "warehouse_id": a["id"], "count_date": w.today})), "")
cnt = made["cnt"]
w.admin.put(f"{INV}/counts/{cnt['id']}", {"lines": [{"product_id": p["id"], "counted_quantity": "10"}]})
audited("count post", lambda: w.admin.post(f"{INV}/counts/{cnt['id']}/post", {}), "")
audited("repack", lambda: w.admin.post(f"{INV}/repacks", {"repack_date": w.today, "branch_id": w.branch_id, "warehouse_id": a["id"],
                                                         "lines": [{"kind": "CONSUME", "product_id": p["id"], "quantity": "1"}, {"kind": "PRODUCE", "product_id": pb["id"], "quantity": "1", "batch_number": f"RP{w.tag}", "expiry_date": later}]}), "repack.")
audited("reason", lambda: w.admin.post(f"{INV}/adjustment-reasons", {"code": f"AU{w.tag}", "name": f"Au {w.tag}"}), "")
audited("count plan", lambda: w.admin.post(f"{INV}/count-plans", {"name": f"AU{w.tag}", "branch_id": w.branch_id, "warehouse_id": a["id"], "frequency_days": 30}), "")
audited("limits", lambda: w.admin.put(f"{INV}/adjustment-limits", {"limits": [{"role_code": "SALES_MANAGER", "max_value": "100"}]}), "")
w.admin.put(f"{INV}/adjustment-limits", {"limits": []})
audited("batch", lambda: w.admin.post("/api/v1/batch-serial/batches", {"product_id": pb["id"], "batch_number": f"AU{w.tag}", "expiry_date": later}), "batch.")
audited("serial", lambda: w.admin.post("/api/v1/batch-serial/serials", {"product_id": ps["id"], "serial_number": f"AU{w.tag}"}), "serial_number.")
# a refused write leaves no row
before = total()
st, b = w.admin.post(f"{INV}/transfers", {**tbase, "from_warehouse_id": a["id"], "to_warehouse_id": b2["id"], "quantity": "9999", "reference_number": f"R{w.tag}"})
c.ok(st >= 400 and total() == before, "a refused transfer leaves no audit row", (st, total() - before))
c.done()
