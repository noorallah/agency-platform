"""TC-MAST-001: a vendor edit keeps all six child collections (an update naming only the phone, then the whole record echoed)."""
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

c = Check("tc_mast_001")
a = api()
v = full_vendor(a)
c.eq(counts(a, v["id"]), {k: 1 for k in VCHILD}, "precondition: one of each")
st, body = a.put(f"{VE}/{v['id']}", {"code": v["code"], "name": v["name"], "phone": "+919800000299"})
c.eq(st, 200, f"update naming only the phone ({message(body)})")
c.eq(counts(a, v["id"]), {k: 1 for k in VCHILD}, "all six still there after the minimal update")
c.eq(must(a.get(f"{VE}/{v['id']}"), "v")["phone"], "+919800000299", "the phone is new")
row = must(a.get(f"{VE}/{v['id']}"), "v")
st, body = a.put(f"{VE}/{v['id']}", vendor_echo(row, phone="+919800000298"))
c.eq(st, 200, f"whole record echoed ({message(body)})")
c.eq(counts(a, v["id"]), {k: 1 for k in VCHILD}, "all six still there after the whole-record update")
row = must(a.get(f"{VE}/{v['id']}"), "v")
c.eq((row["bank_accounts"][0]["account_number"], row["tax_details"][0]["pan"], row["notes"][0]["note"].startswith("Created")), ("000111222333", "ABCDE1234F", True), "contents intact")
c.done()
