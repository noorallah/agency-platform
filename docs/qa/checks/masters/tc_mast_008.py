"""TC-MAST-008: a carton barcode finds its product (Case of 12)."""
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

c = Check("tc_mast_008")
a = api()
p = product(a)
units = {u["code"]: u for u in rows_of(a.get("/api/v1/uom-framework/uoms?page_size=100"))}
bc = "89" + str(uuid.uuid4().int)[:11]
made = a.post(f"{UOM}/products/{p['id']}/packaging-levels", {"level_name": "Case", "conversion_to_base_factor": "12", "uom_id": units["CASE"]["id"], "barcode": bc})
c.eq(made[0], 201, f"Case level made ({message(made[1])})")
found = must(a.get(f"{UOM}/barcode-lookup?code={bc}"), "lookup")
c.eq((found["product_id"], found["level_name"], D(found["base_quantity"])), (p["id"], "Case", D(12)), "resolves to the product, level Case, 12 base units")
c.eq(found["matched_field"], "barcode", "matched on the barcode")
c.eq(a.get(f"{UOM}/barcode-lookup?code=0000{bc}")[0] in (404, 422), True, "an unknown code is not found")
c.done()
