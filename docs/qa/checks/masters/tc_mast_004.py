"""TC-MAST-004: a rename keeps a branch's address, city, GST registration, PAN and default flag (TEST02, own branch)."""
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

c = Check("tc_mast_004")
a = api("admin2")
t = tag()
src = by_code(a, BR, two()["branch_code"])
ref = must(a.get(f"{BR}/{src['id']}"), "fixture branch")
body = {"code": f"BR{t}", "name": f"Keep Branch {t}", "address_line1": "1 Keep Street", "address_line2": "Keep Nagar",
        "country_id": ref["country_id"], "state_id": ref["state_id"], "district_id": ref["district_id"], "city_id": ref["city_id"],
        "gst_registration": True, "pan": "ABCDE1234F", "is_default": True}
br = must(a.post(BR, body), "branch")
def keep(row):
    return (row["address_line1"], row["address_line2"], row["city_id"], row["state_id"], row["gst_registration"], row["pan"], row["is_default"])
want = ("1 Keep Street", "Keep Nagar", ref["city_id"], ref["state_id"], True, "ABCDE1234F", True)
c.eq(keep(must(a.get(f"{BR}/{br['id']}"), "b")), want, "precondition: described branch")
st, resp = a.put(f"{BR}/{br['id']}", {"code": br["code"], "name": f"Kept Branch renamed {t}"})
c.eq(st, 200, f"rename naming only the name ({message(resp)})")
row = must(a.get(f"{BR}/{br['id']}"), "b")
c.eq(row["name"], f"Kept Branch renamed {t}", "renamed")
c.eq(keep(row), want, "address, city, GST registration, PAN and default unchanged after the minimal rename")
whole = echo("BranchUpdate", row, name=f"Kept Again {t}")
st, resp = a.put(f"{BR}/{br['id']}", whole)
c.eq(st, 200, f"whole-record rename ({message(resp)})")
c.eq(keep(must(a.get(f"{BR}/{br['id']}"), "b")), want, "and unchanged after the whole-record rename")
c.done()
