"""Probe (round 11): adjustment reasons and limits as settings (STK-7, STK-8).

A reason removed or switched off while a request names it, a reason's
code given back and taken again; and what the list of limits accepts, whom
a limit of nothing binds, and who may write it.
"""
from _inv import *
from _flow import *

c = Check("p_reason_limit_settings")
w = World()
store = client("store")
viewer = client("viewer")
R = f"{INV}/adjustment-reasons"
LIM = f"{INV}/adjustment-limits"
REQ = f"{INV}/adjustment-requests"
wh = w.warehouse()
p = w.product()
free = w.product("Z")
w.stock_in(wh["id"], p["id"], 50, 10)
w.stock_in(wh["id"], free["id"], 50, 0)
base = {"branch_id": w.branch_id, "warehouse_id": wh["id"], "product_id": p["id"], "transaction_date": w.today}


def wo(qty: str, ref: str, reason: str = "DAMAGE", **extra: str) -> dict:
    """A write-off body."""
    return {**base, "quantity": qty, "reason": reason, "reference_number": f"{ref}{w.tag}", **extra}


def reason_row(code: str, active_only: bool = False) -> dict | None:
    """The reason as the list shows it."""
    st, b = w.admin.get(f"{R}?active_only={'true' if active_only else 'false'}")
    return next((row for row in data(b) if row["code"] == code), None)


# ---- reasons ---------------------------------------------------------
for label, body in (
    ("a name of only spaces", {"code": f"NA{w.tag}", "name": "   "}),
    ("an empty name", {"code": f"NB{w.tag}", "name": ""}),
    ("a code of one letter", {"code": "Q", "name": "Short"}),
    ("a code with a space in it", {"code": f"N C{w.tag}", "name": "Spaced"}),
    ("a field nobody declared", {"code": f"ND{w.tag}", "name": "Extra", "colour": "red"}),
    ("a code that is a number", {"code": 12345, "name": "Numbered"}),
    ("a name that is a number", {"code": f"NE{w.tag}", "name": 12345}),
):
    st, b = w.admin.post(R, body)
    c.eq(st, 422, f"a reason with {label} is refused")
    if st == 201:
        w.admin.delete(f"{R}/{data(b)['id']}")

code = f"RX{w.tag}"
st, b = w.admin.post(R, {"code": code, "name": "Probe reason"})
c.eq(st, 201, "a reason of the firm's own is saved")
mine = data(b)

# removed while a request names it
st, b = store.post(REQ, {"kind": "WRITE_OFF", "write_off": wo("2", "SA", code)})
c.eq(st, 201, "a request naming it is accepted")
held = data(b)
st, b = w.admin.delete(f"{R}/{mine['id']}")
c.eq(st, 200, "the reason is removed while the request waits")
c.eq(reason_row(code), None, "it is no longer listed")
st, b = w.admin.delete(f"{R}/{mine['id']}")
c.eq(st, 404, "it cannot be removed twice")
st, b = w.admin.put(f"{R}/{mine['id']}", {"code": code, "name": "Back"})
c.eq(st, 404, "or changed once removed")
answer = w.admin.post(f"{REQ}/{held['id']}/approve", {})
c.refused(answer, 422, "not an active stock adjustment reason", "approving the request is refused, naming the reason")
c.eq(w.qty(p["id"], wh["id"]), D(50), "nothing moved")
st, b = w.admin.get(f"{REQ}?status=PENDING")
c.ok(any(row["id"] == held["id"] for row in data(b)), "and the request still waits")
answer = store.post(f"{INV}/write-offs", wo("1", "SB", code))
c.refused(answer, 422, "not an active stock adjustment reason", "a write-off naming a removed reason is refused")

# the code is free again
st, b = w.admin.post(R, {"code": code, "name": "Probe reason again"})
c.eq(st, 201, "the removed reason's code can be taken again")
again = data(b)
st, b = w.admin.post(f"{REQ}/{held['id']}/approve", {})
c.eq(st, 200, "and the waiting request is approved under it")
c.eq(w.qty(p["id"], wh["id"]), D(48), "2 pieces left")

# switched off while a request names it
st, b = store.post(REQ, {"kind": "WRITE_OFF", "write_off": wo("3", "SC", code)})
c.eq(st, 201, "a second request names the reason")
waiting = data(b)
st, b = w.admin.put(f"{R}/{again['id']}", {"code": code, "name": "Probe reason again", "is_active": False})
c.eq(st, 200, "the reason is switched off")
c.eq(reason_row(code, active_only=True), None, "the list of active reasons leaves it out")
c.ok(reason_row(code) is not None, "the full list still shows it")
answer = w.admin.post(f"{REQ}/{waiting['id']}/approve", {})
c.refused(answer, 422, "not an active stock adjustment reason", "approving is refused while the reason is off")
answer = store.post(REQ, {"kind": "WRITE_OFF", "write_off": wo("1", "SD", code)})
c.refused(answer, 422, "not an active stock adjustment reason", "a new request naming it is refused")
c.eq(w.qty(p["id"], wh["id"]), D(48), "nothing moved")
st, b = w.admin.put(f"{R}/{again['id']}", {"code": code, "name": "Probe reason again", "is_active": True})
c.eq(st, 200, "the reason is switched on again")
st, b = w.admin.post(f"{REQ}/{waiting['id']}/approve", {})
c.eq(st, 200, "and the request is approved")
c.eq(w.qty(p["id"], wh["id"]), D(45), "3 pieces left")

# a code changed to one that is taken
st, b = w.admin.put(f"{R}/{again['id']}", {"code": "DAMAGE", "name": "Probe reason again"})
c.eq(st, 409, "a reason cannot take a code another holds")
st, b = w.admin.put(f"{R}/{again['id']}", {"code": code, "name": "   "})
c.eq(st, 422, "a reason cannot be renamed to only spaces")
row = reason_row(code)
c.eq(row and row["name"], "Probe reason again", "it keeps its name")
w.admin.delete(f"{R}/{again['id']}")

# ---- limits ----------------------------------------------------------
st, b = w.admin.get(LIM)
c.eq(st, 200, "the limits read")
kept = [{"role_code": row["role_code"], "max_value": row["max_value"]} for row in data(b)]
try:
    for label, limits in (
        ("a negative limit", [{"role_code": "INVENTORY_MANAGER", "max_value": "-1"}]),
        ("a limit that is not a number", [{"role_code": "INVENTORY_MANAGER", "max_value": "lots"}]),
        ("a limit in tenths of a paisa", [{"role_code": "INVENTORY_MANAGER", "max_value": "10.005"}]),
        ("a role of only spaces", [{"role_code": "   ", "max_value": "10"}]),
        ("an empty role", [{"role_code": "", "max_value": "10"}]),
        ("a role nobody has", [{"role_code": f"NO_SUCH_{w.tag}", "max_value": "10"}]),
        ("one role twice", [{"role_code": "INVENTORY_MANAGER", "max_value": "10"}, {"role_code": "INVENTORY_MANAGER", "max_value": "20"}]),
        ("one role twice, once with spaces round it", [{"role_code": "INVENTORY_MANAGER", "max_value": "10"}, {"role_code": " INVENTORY_MANAGER ", "max_value": "20"}]),
        ("no amount", [{"role_code": "INVENTORY_MANAGER"}]),
    ):
        st, b = w.admin.put(LIM, {"limits": limits})
        c.eq(st, 422, f"a list with {label} is refused")
    st, b = w.admin.get(LIM)
    c.eq([row["role_code"] for row in data(b)], [row["role_code"] for row in kept], "a refused list changed nothing")

    for who, api in (("the warehouse role", store), ("a viewer", viewer)):
        st, b = api.put(LIM, {"limits": []})
        c.eq(st, 403, f"{who} may not write the limits")
    st, b = store.get(LIM)
    c.eq(st, 200, "the warehouse role may read them")

    # a role written in lower case binds the person who holds it, or is refused
    st, b = w.admin.put(LIM, {"limits": [{"role_code": "inventory_manager", "max_value": "5"}]})
    if st == 200:
        c.eq([row["role_code"] for row in data(b)], ["INVENTORY_MANAGER"], "a role typed in lower case is kept as the role's own code")
        answer = store.post(f"{INV}/write-offs", wo("1", "LA"))
        c.refused(answer, 422, "limit", "and binds the person holding it (10 against a limit of 5)")
    else:
        c.eq(st, 422, "a role typed in lower case is refused by name")

    # a limit of nothing
    st, b = w.admin.put(LIM, {"limits": [{"role_code": "INVENTORY_MANAGER", "max_value": "0"}]})
    c.eq(st, 200, "a limit of 0 is saved")
    answer = store.post(f"{INV}/write-offs", wo("1", "LB"))
    c.refused(answer, 422, "limit", "one piece worth 10 is over a limit of 0")
    if answer[0] == 422:
        details = str(answer[1])
        c.ok("needs_approval" in details, "the refusal says it can be sent for approval", details[:200])
    st, b = store.post(f"{INV}/write-offs", {**wo("1", "LC"), "product_id": free["id"]})
    c.eq(st, 201, "stock that cost nothing is worth nothing, so it is within a limit of 0")
    st, b = w.admin.post(f"{INV}/write-offs", wo("1", "LD"))
    c.eq(st, 201, "the administrator, with no limit of their own, still posts")
    c.eq(w.qty(p["id"], wh["id"]), D(44), "1 piece left by the administrator's post only")

    # the whole list is replaced
    st, b = w.admin.put(LIM, {"limits": [{"role_code": "FIRM_MANAGER", "max_value": "7.5"}]})
    c.eq(st, 200, "a list naming another role is saved")
    c.eq([(row["role_code"], D(row["max_value"])) for row in data(b)], [("FIRM_MANAGER", D("7.5"))], "the role left out has no limit now")
    st, b = store.post(f"{INV}/write-offs", wo("1", "LE"))
    c.eq(st, 201, "so the warehouse role posts again")
    st, b = w.admin.put(LIM, {"limits": []})
    c.eq(st, 200, "an empty list is saved")
    c.eq(data(b), [], "and nobody has a limit")
finally:
    w.admin.put(LIM, {"limits": kept})
c.done()
