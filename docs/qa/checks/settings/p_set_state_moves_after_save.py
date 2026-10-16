"""Probe: Promotions, Route builder, Approval levels, Numbering series move on save.

Each record is made through its own endpoint, the section is read again, and the
record is then taken away (numbering rule and offer deleted, rule list replaced
by what it held, round emptied); every write is read back.
"""

from _settings import Check, count_of, data, lead, message, steps, suffix, who

c = Check("p_set_state_moves_after_save")
ready = who("ready_admin", "ready")


def read_step(section: str, code: str) -> str:
    """Return one step's detail line."""
    return steps(ready, section)[code][1]


# Approval levels: replace SALES_ORDER's rules with one level, read back, put back.
path = "/api/v1/approvals/rules/SALES_ORDER"
status, body = ready.get("/api/v1/approvals/rules")
held = [
    {"level": r["level"], "min_amount": r["min_amount"], "role_code": r["role_code"]}
    for r in (data(body) if status == 200 else [])
    if r["document_type"] == "SALES_ORDER"
]
before = read_step("firm", "approval-levels")
got, answer = ready.put(
    path, {"rules": [{"level": 1, "min_amount": "1000", "role_code": "SALES_MANAGER"}]}
)
if c.eq(got, 200, f"PUT {path} {message(answer)[:150]}"):
    rows = [r for r in data(answer) if r["document_type"] == "SALES_ORDER"]
    c.eq(len(rows), 1, "approval rule read back from the PUT answer")
    again = ready.get("/api/v1/approvals/rules")
    c.eq(
        len([r for r in data(again[1]) if r["document_type"] == "SALES_ORDER"]),
        1,
        "approval rule listed",
    )
    after = read_step("firm", "approval-levels")
    c.eq(
        lead(after),
        lead(before) + 1 - len(held),
        f"approval-levels {before!r} -> {after!r}",
    )
got, answer = ready.put(path, {"rules": held})
if c.eq(got, 200, f"PUT {path} back {message(answer)[:150]}"):
    c.eq(
        read_step("firm", "approval-levels"),
        before,
        "approval-levels back to what it was",
    )

# Numbering series: one more rule on a document type, then deleted.
status, body = ready.get("/api/v1/document-framework/document-types?page=1&page_size=1")
dtype = data(body)[0]["id"] if status == 200 and data(body) else None
before = read_step("firm", "numbering-series")
if c.ok(dtype, "a document type exists"):
    code = f"SET{suffix(5).upper()}"
    got, answer = ready.post(
        "/api/v1/document-framework/numbering-rules",
        {
            "document_type_id": dtype,
            "code": code,
            "name": f"Settings check {suffix(4)}",
            "prefix": "ZZ",
            "include_financial_year": True,
        },
    )
    if c.eq(got, 201, f"POST numbering rule {message(answer)[:150]}"):
        rid = data(answer)["id"]
        c.eq(data(answer)["code"], code, "numbering rule echoes its code")
        after = read_step("firm", "numbering-series")
        c.eq(
            lead(after),
            lead(before) + 1 if before[0].isdigit() else 1,
            f"numbering-series {before!r} -> {after!r}",
        )
        got = ready.delete(f"/api/v1/document-framework/numbering-rules/{rid}")[0]
        c.eq(got, 204, "numbering rule deleted")
        c.eq(
            read_step("firm", "numbering-series"),
            before,
            "numbering-series back to what it was",
        )

# Promotions: one ACTIVE offer, then deleted.
before = read_step("pricing", "promotions")
got, answer = ready.post(
    "/api/v1/promotions",
    {
        "code": f"SET-{suffix(5).upper()}",
        "name": f"Settings check {suffix(4)}",
        "status": "ACTIVE",
        "effective_from": "2020-01-01",
        "conditions": [],
        "actions": [{"action_type": "LINE_DISCOUNT_PERCENT", "percent": "5"}],
    },
)
if c.eq(got, 201, f"POST promotion {message(answer)[:150]}"):
    pid = data(answer)["id"]
    after = read_step("pricing", "promotions")
    c.eq(
        count_of(after, "offer"),
        count_of(before, "offer") + 1,
        f"promotions {before!r} -> {after!r}",
    )
    c.eq(
        count_of(after, "running") if "running" in after else 0,
        (count_of(before, "running") if "running" in before else 0) + 1,
        "one more offer running",
    )
    c.eq(ready.get(f"/api/v1/promotions/{pid}")[0], 200, "promotion reads back")
    c.eq(ready.delete(f"/api/v1/promotions/{pid}")[0], 200, "promotion deleted")
    c.eq(read_step("pricing", "promotions"), before, "promotions back to what it was")

# Route builder: a customer onto a new round, then taken off.
status, body = ready.get("/api/v1/sales-territories/hierarchy-levels")
levels = data(body)["levels"] if status == 200 else []
cust = data(ready.get("/api/v1/customers?page=1&page_size=1")[1])
before = read_step("territories", "route-builder")
if c.ok(levels and cust, "a hierarchy level and a customer exist"):
    got, answer = ready.post(
        "/api/v1/sales-territories",
        {
            "code": f"S{suffix(5)}",
            "name": f"Settings check round {suffix(4)}",
            "hierarchy_level_id": levels[0]["id"],
        },
    )
    if c.eq(got, 201, f"POST territory {message(answer)[:150]}"):
        tid = data(answer)["id"]
        got, answer = ready.put(
            f"/api/v1/sales-territories/{tid}/customers",
            {"customer_ids": [cust[0]["id"]]},
        )
        if c.eq(got, 200, f"PUT round customers {message(answer)[:150]}"):
            listed = data(ready.get(f"/api/v1/sales-territories/{tid}/customers")[1])
            c.eq(len(listed), 1, "round holds the shop read back")
            after = read_step("territories", "route-builder")
            c.eq(
                count_of(after, "shop"),
                count_of(before, "shop") + 1,
                f"route-builder {before!r} -> {after!r}",
            )
            c.eq(
                count_of(after, "round"),
                count_of(before, "round") + 1,
                "one more round",
            )
        got, answer = ready.put(
            f"/api/v1/sales-territories/{tid}/customers", {"customer_ids": []}
        )
        c.eq(got, 200, f"PUT round emptied {message(answer)[:150]}")
        c.eq(
            read_step("territories", "route-builder"),
            before,
            "route-builder back to what it was",
        )
        c.eq(
            ready.delete(f"/api/v1/sales-territories/{tid}")[0] in (200, 204),
            True,
            "territory deleted",
        )
c.done()
