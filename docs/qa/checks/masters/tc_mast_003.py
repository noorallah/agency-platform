"""TC-MAST-003: a product's slots (category, tax profile group, base/inventory/sales/purchase units) read back as set. Names-not-ids is screen-only."""
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

c = Check("tc_mast_003")
a = api()
t = tag()
cat = must(a.post(f"{PR}/categories", {"code": f"PC{t}", "name": f"Shelf {t}"}), "category")
units = {u["code"]: u for u in rows_of(a.get("/api/v1/uom-framework/uoms?page_size=100"))}
p = product(a, category_id=cat["id"], purchase_uom_id=units["BOX"]["id"], base_uom_id=units["PIECE"]["id"])
row = must(a.get(f"{PR}/{p['id']}"), "p")
c.eq(row["category_id"], cat["id"], "category held")
c.eq(row["tax_profile_group_code"], "GST_18_LOCAL", "tax profile group held")
c.eq((row["base_uom_id"], row["inventory_uom_id"], row["sales_uom_id"]), (units["PIECE"]["id"],) * 3, "base, inventory and sales units are PIECE")
c.eq(row["purchase_uom_id"], units["BOX"]["id"], "purchase unit is BOX")
listed = [r for r in rows_of(a.get(f"{PR}?search={p['code']}")) if r["id"] == p["id"]]
c.eq(len(listed), 1, "the product is listed")
c.eq(row["unit_code"], "PIECE", "the unit also reads as a code")
c.done()
