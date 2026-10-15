"""Probe: a second firm's administrator can neither read nor post into firm one's journals, reports or years."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _fin import *

c = Check("p_fin_other_firm")
a = admin()
b = admin("admin2")
one = state(MODULE)["firm_id"]
two = state(MODULE)["firm2_id"]

st, made = a.post(JE, draft_body(a, [("5000", "9.00", "0"), ("1000", "0", "9.00")]))
entry = data(made)
c.eq(st, 201, "firm one drafts an entry")
per = period_of(a)
fy = rows_of(a.get(f"{FIN}/financial-years"))[0]

# B's own context cannot see or touch it
c.eq(b.get(f"{JE}/{entry['id']}")[0], 404, "B reads A's entry inside B's firm: 404")
c.eq(b.post(f"{JE}/{entry['id']}/post", {})[0], 404, "B cannot post A's draft from B's firm: 404")
c.eq(b.delete(f"{JE}/{entry['id']}")[0], 404, "B cannot delete it: 404")
c.ok(entry["id"] not in [e["id"] for e in rows_of(b.get(f"{JE}?page_size=100"))], "A's entry is in no list of B's")
# B names firm one in the header
bx = b.inside(one)
for what, got in (
    ("read the entry", bx.get(f"{JE}/{entry['id']}")),
    ("list journals", bx.get(JE)),
    ("read the trial balance", bx.get(f"{FIN}/trial-balance?accounting_period_id={per['id']}")),
    ("read the P&L", bx.get(f"{FIN}/profit-loss?accounting_period_id={per['id']}")),
    ("read payments", bx.get(PAY)),
    ("read the years", bx.get(f"{FIN}/financial-years")),
):
    c.ok(got[0] in (403, 404), f"B naming firm one cannot {what} (403/404)", got[0])
c.eq(bx.post(f"{JE}/{entry['id']}/post", {})[0] in (403, 404), True, "B naming firm one cannot post A's draft")
c.eq(bx.post(JE, draft_body(a, [("5000", "1.00", "0"), ("1000", "0", "1.00")]))[0] in (403, 404), True, "B naming firm one cannot create an entry there")
c.eq(bx.post(f"{FIN}/financial-years/{fy['id']}/close", {})[0] in (403, 404), True, "B naming firm one cannot close its year")
# B posting with A's ids in B's own firm
c.eq(b.post(JE, draft_body(a, [("5000", "1.00", "0"), ("1000", "0", "1.00")]))[0] in (400, 404, 422), True, "A's period and account ids are refused in B's firm")
# B's trial balance is B's
tb_b = tb(b, period_of(b))
c.eq(sums(tb_b)[0], sums(tb_b)[1], "B's own trial balance balances")
st, after = a.get(f"{JE}/{entry['id']}")
c.eq(data(after)["status"], "DRAFT", "A's draft is untouched")
c.done()
