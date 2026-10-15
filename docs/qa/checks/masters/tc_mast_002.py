"""TC-MAST-002: vendor categories and types load, accept a row, and a vendor takes them with its six collections intact."""
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

c = Check("tc_mast_002")
a = api()
t = tag()
c.eq(a.get(f"{VE}/categories")[0], 200, "categories list loads")
c.eq(a.get(f"{VE}/types")[0], 200, "types list loads")
cat = must(a.post(f"{VE}/categories", {"code": f"CAT{t}", "name": f"Category {t}"}), "category")
typ = must(a.post(f"{VE}/types", {"code": f"TYP{t}", "name": f"Type {t}"}), "type")
c.ok(cat["id"] in [r["id"] for r in rows_of(a.get(f"{VE}/categories?search=CAT{t}"))], "the new category is listed")
c.ok(typ["id"] in [r["id"] for r in rows_of(a.get(f"{VE}/types?search=TYP{t}"))], "the new type is listed")
v = full_vendor(a)
st, body = a.put(f"{VE}/{v['id']}", {"code": v["code"], "name": v["name"], "category_id": cat["id"], "type_id": typ["id"]})
c.eq(st, 200, f"category and type set ({message(body)})")
row = must(a.get(f"{VE}/{v['id']}"), "v")
c.eq((row["category_id"], row["type_id"]), (cat["id"], typ["id"]), "both held")
c.eq(counts(a, v["id"]), {k: 1 for k in VCHILD}, "the six collections are still there")
c.done()
