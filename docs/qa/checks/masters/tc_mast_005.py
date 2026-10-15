"""TC-MAST-005: a rename keeps a warehouse's capacity and capability flags (TEST02, own branch and warehouse)."""
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

c = Check("tc_mast_005")
a = api("admin2")
t = tag()
br = must(a.post(BR, {"code": f"WB{t}", "name": f"Warehouse branch {t}"}), "branch")
flags = {"temperature_controlled": True, "cold_storage": True, "hazardous_storage": False, "has_receiving_area": True,
         "has_dispatch_area": True, "has_returns_area": False, "has_inspection_area": True, "has_packing_area": False, "has_loading_dock": True}
wh = must(a.post(WH, {"branch_id": br["id"], "code": f"WH{t}", "name": f"Keep Warehouse {t}", "capacity": "1000", "capacity_unit": "SQFT", "is_default": True, **flags}), "warehouse")
def keep(row):
    return ({k: row[k] for k in flags}, D(row["capacity"]), row["capacity_unit"], row["is_default"])
want = (flags, D(1000), "SQFT", True)
c.eq(keep(must(a.get(f"{WH}/{wh['id']}"), "w")), want, "precondition: described warehouse")
st, resp = a.put(f"{WH}/{wh['id']}", {"branch_id": br["id"], "code": wh["code"], "name": f"Renamed {t}"})
c.eq(st, 200, f"rename naming only the name ({message(resp)})")
row = must(a.get(f"{WH}/{wh['id']}"), "w")
c.eq(row["name"], f"Renamed {t}", "renamed")
c.eq(keep(row), want, "capacity, default and every flag as listed after the minimal rename")
st, resp = a.put(f"{WH}/{wh['id']}", echo("WarehouseUpdate", row, name=f"Renamed again {t}"))
c.eq(st, 200, f"whole-record rename ({message(resp)})")
c.eq(keep(must(a.get(f"{WH}/{wh['id']}"), "w")), want, "and as listed after the whole-record rename")
nocap = a.post(WH, {"branch_id": br["id"], "code": f"WN{t}", "name": f"No capacity {t}"})
c.eq(nocap[0], 201, f"a warehouse with no capacity can be saved ({message(nocap[1])})")
c.done()
