"""TC-MAST-006: an import with one bad row imports nothing (the batch endpoint the Import dialog calls; the copy icon is screen-only)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _mst import *
import uuid

UOM = "/api/v1/uom-framework"

VCHILD = {"contacts": ("contacts", "VendorContactInput"), "addresses": ("addresses", "VendorAddressInput"),
          "bank_accounts": ("banking", "VendorBankInput"), "tax_details": ("tax", "VendorTaxInput"),
          "attachments": ("attachments", "VendorAttachmentInput"), "notes": ("notes", "VendorNoteInput")}


def full_vendor(a: Api, **extra: object) -> dict:
    """A vendor with one of each of the six child collections."""
    t = tag()
    return must(a.post(VE, {
        "code": f"VM{t}", "name": f"Supply Check {t}", "phone": "+919800000200",
        "contacts": [{"name": "Vendor Contact", "mobile": "+919800000201", "is_primary": True}],
        "addresses": [{"address_type": "OFFICE", "address_line1": "7 Supplier Lane", "is_primary": True}],
        "banking": [{"bank_name": "Fixture Bank", "account_name": f"Supply Check {t}", "account_number": "000111222333", "ifsc": "FXBK0000001", "is_primary": True}],
        "tax": [{"pan": "ABCDE1234F", "is_primary": True}],
        "attachments": [{"file_name": "agreement.pdf", "file_url": "https://example.invalid/agreement.pdf"}],
        "notes": [{"note": f"Created by the check {t}."}], **extra}), "vendor")


def counts(a: Api, vid: str) -> dict[str, int]:
    """How many of each child collection a vendor holds."""
    row = must(a.get(f"{VE}/{vid}"), "vendor")
    return {k: len(row[k] or []) for k in VCHILD}


def vendor_echo(row: dict, **changes: object) -> dict:
    """An update body made of everything the vendor holds, as the screen sends it."""
    keep = schema_fields("VendorUpdate")
    body = {k: v for k, v in row.items() if k in keep}
    for resp, (field, schema) in VCHILD.items():
        ok = schema_fields(schema)
        body[field] = [{k: v for k, v in r.items() if k in ok} for r in row[resp]]
    body.update(changes)
    return body

c = Check("tc_mast_006")
a = api("admin2")
t = tag()
rows = [{"code": f"I{n}{t}", "name": f"Import {n} {t}", "address_line1": f"{n} Import Road", "currency_code": "INR", "status": "ACTIVE"} for n in range(1, 5)]
dup = {"code": by_code(a, BR, two()["branch_code"])["code"], "name": f"Clash {t}", "address_line1": "x", "currency_code": "INR", "status": "ACTIVE"}
r = a.post(f"{BR}/import", {"records": rows + [dup]})
c.ok(r[0] in (409, 422), "five rows, the fifth reusing an existing code: refused", f"{r[0]} {message(r[1])}")
c.ok(t in message(r[1]) or "already" in message(r[1]).lower() or "exists" in message(r[1]).lower(), "and the message says why", message(r[1]))
c.eq(rows_of(a.get(f"{BR}?search={t}")), [], "nothing from the first four was imported")
ok = a.post(f"{BR}/import", {"records": rows})
c.ok(ok[0] in (200, 201), f"the clean four go in", f"{ok[0]} {message(ok[1])}")
got = sorted(r["code"] for r in rows_of(a.get(f"{BR}?search={t}")))
c.eq(got, sorted(r["code"] for r in rows), "all four rows exist")
c.done()
