"""TC-MAST-013: a customer's bank accounts (replaced as a whole, masked for readers without CUSTOMER_MANAGE_BANK_DETAILS, masked in the audit trail) and files (references, soft delete)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _mst import *
from _col import receipt, closing, position, journal
import re
from datetime import timedelta

IMP = "/api/v1/imports"

c = Check("tc_mast_013")
a, m, acc = api(), api("manager"), api("accountant")
d = described(a)
num = "1234567890123456"
put = a.put(f"{CU}/{d['id']}/bank-accounts", {"accounts": [{"bank_name": "Test Bank", "account_name": "Master Check", "account_number": num, "ifsc": "TEST0001234", "is_primary": True}]})
c.eq(put[0], 200, f"account saved ({message(put[1])})")
c.eq([x["account_number"] for x in rows_of(a.get(f"{CU}/{d['id']}/bank-accounts"))], [num], "the administrator sees the number whole")
for who, name in ((m, "sales manager"), (acc, "accountant")):
    got = who.get(f"{CU}/{d['id']}/bank-accounts")
    c.eq(got[0], 200, f"{name} reads the tab")
    rows = rows_of(got) if got[0] == 200 else []
    c.eq([(x["account_number"].endswith(num[-4:]) and num not in x["account_number"], x["masked"]) for x in rows], [(True, True)], f"{name} sees only the last four digits, flagged masked")
put2 = a.put(f"{CU}/{d['id']}/bank-accounts", {"accounts": [{"bank_name": "Second", "account_name": "Master Check", "account_number": "9999888877", "is_primary": True}]})
c.eq([x["bank_name"] for x in rows_of(a.get(f"{CU}/{d['id']}/bank-accounts"))], ["Second"], "the list is replaced as a whole")
trail = json.dumps(rows_of(a.get(f"/api/v1/audit-logs?entity_id={d['id']}&page_size=50")))
c.ok(num not in trail and "9999888877" not in trail, "the audit trail never shows a whole account number", trail[:200])
fl = a.post(f"{CU}/{d['id']}/attachments", {"files": [{"file_name": "kyc.pdf", "mime_type": "application/pdf", "file_path": "files/kyc.pdf", "caption": "KYC"}]})
c.eq(fl[0], 201 if fl[0] == 201 else 200, f"file reference saved ({message(fl[1])})")
files = rows_of(a.get(f"{CU}/{d['id']}/attachments"))
c.eq([(f["file_name"], f["caption"]) for f in files], [("kyc.pdf", "KYC")], "the reference is listed")
c.ok(a.delete(f"{CU}/{d['id']}/attachments/{files[0]['id']}")[0] in (200, 204), "and can be deleted")
c.eq(rows_of(a.get(f"{CU}/{d['id']}/attachments")), [], "gone from the list")
c.eq(m.put(f"{CU}/{d['id']}/bank-accounts", {"accounts": []})[0], 403, "a sales manager cannot replace the accounts")
c.done()
