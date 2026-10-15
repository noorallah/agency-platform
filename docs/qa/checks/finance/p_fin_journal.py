"""Probe: a manual journal drafts, posts and reverses; unbalanced is refused; reversal mirrors; double reversal refused."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _fin import *

c = Check("p_fin_journal")
a = admin()
viewer = admin("viewer")
per = period_of(a)
base_tb = tb(a, per)
cash0, purch0 = closing(base_tb, "1000"), closing(base_tb, "5000")

# unbalanced and malformed drafts are refused and write nothing
n0 = journal_count(a)
st, body = a.post(JE, draft_body(a, [("5000", "100.00", "0"), ("1000", "0", "90.00")]))
c.eq(st, 422, "an unbalanced draft is refused")
c.ok("not balanced" in message(body).lower(), "the refusal says not balanced", message(body))
c.eq(a.post(JE, draft_body(a, [("5000", "0", "0"), ("1000", "0", "0")]))[0], 422, "an all-zero entry is refused")
c.eq(a.post(JE, draft_body(a, [("5000", "100.00", "0")]))[0], 422, "a one-sided single line is refused")
c.eq(a.post(JE, draft_body(a, [("5000", "100.00", "50.00"), ("1000", "0", "50.00")]))[0], 422, "a line with both a debit and a credit is refused")
c.eq(a.post(JE, draft_body(a, [("5000", "-100.00", "0"), ("1000", "0", "-100.00")]))[0], 422, "negative amounts are refused")
bad_ref = draft_body(a, [("5000", "100.00", "0"), ("1000", "0", "100.00")], reference="SI-HAND-1")
c.refused(a.post(JE, bad_ref), 422, "JV-", "a hand reference outside JV- is refused")
c.eq(journal_count(a), n0, "no refusal left a row behind")
c.eq(viewer.post(JE, draft_body(a, [("5000", "10.00", "0"), ("1000", "0", "10.00")]))[0], 403, "a Viewer cannot draft")

# draft: nothing on the books
body = draft_body(a, [("5000", "100.25", "0"), ("1000", "0", "100.25")])
st, made = a.post(JE, body)
c.eq(st, 201, "a balanced draft is saved")
entry = data(made)
c.eq(entry["status"], "DRAFT", "it starts as a draft")
c.eq((D(entry["total_debit"]), D(entry["total_credit"])), (D("100.25"), D("100.25")), "totals 100.25 each side")
c.eq(closing(tb(a, per), "5000"), purch0, "a draft moves no balance")
c.eq(a.post(JE, {**body})[0] in (409, 422), True, "the same reference again is refused")
c.eq(viewer.post(f"{JE}/{entry['id']}/post", {})[0], 403, "a Viewer cannot post")

# post
st, posted = a.post(f"{JE}/{entry['id']}/post", {})
c.eq(st, 200, "the draft posts")
c.eq(data(posted)["status"], "POSTED", "status POSTED")
after = tb(a, per)
c.eq(closing(after, "5000") - purch0, D("100.25"), "Purchases up by 100.25 Dr")
c.eq(closing(after, "1000") - cash0, D("-100.25"), "Cash down by 100.25")
dr, cr = sums(after)
c.eq(dr, cr, "the trial balance still balances to the paisa")
c.eq(a.post(f"{JE}/{entry['id']}/post", {})[0] in (409, 422), True, "posting twice is refused")
c.eq(a.delete(f"{JE}/{entry['id']}")[0] in (409, 422), True, "a posted entry cannot be deleted")
c.eq(a.call("PATCH", f"{JE}/{entry['id']}", {"description": "edited"})[0] in (409, 422), True, "a posted entry cannot be edited")

# reverse
st, rev = a.post(f"{JE}/{entry['id']}/reverse", {"reference_number": f"JV-REV-{suffix(5)}"})
c.eq(st, 201, "reversal is created")
rev = data(rev)
c.eq(rev["status"], "POSTED", "the reversal is posted")
c.eq(rev["reversal_of_id"], entry["id"], "it points at the original")
orig_lines = {l["ledger_account_id"]: (D(l["debit_amount"]), D(l["credit_amount"])) for l in entry["lines"]}
mirror = {l["ledger_account_id"]: (D(l["debit_amount"]), D(l["credit_amount"])) for l in rev["lines"]}
c.eq(mirror, {k: (cr_, dr_) for k, (dr_, cr_) in orig_lines.items()}, "each line is the original with sides swapped")
back = tb(a, per)
c.eq(closing(back, "5000"), purch0, "Purchases back to where it was")
c.eq(closing(back, "1000"), cash0, "Cash back to where it was")
orig = data(a.get(f"{JE}/{entry['id']}")[1])
c.ok(orig["status"] in ("REVERSED", "POSTED"), "the original reads", orig["status"])
c.refused(a.post(f"{JE}/{entry['id']}/reverse", {"reference_number": f"JV-REV-{suffix(5)}"}), 422, "", "a second reversal of the same entry is refused")
c.eq(journal_count(a), n0 + 2, "exactly the entry and its one reversal were added")

# a draft can be edited? deleted?
st, d2 = a.post(JE, draft_body(a, [("5000", "7.00", "0"), ("1000", "0", "7.00")]))
d2 = data(d2)
c.eq(a.delete(f"{JE}/{d2['id']}")[0], 204, "a draft can be deleted")
c.eq(a.get(f"{JE}/{d2['id']}")[0], 404, "and is gone")
c.done()
