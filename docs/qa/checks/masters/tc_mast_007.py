"""TC-MAST-007: export columns are the importer's columns and re-import by branch code works. The Sample file download, the save dialog and the notice are screen-only (the desktop builds them)."""
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

c = Check("tc_mast_007")
a = api("admin2")
t = tag()
s, raw = a.raw(f"{BR}/export")
c.eq(s, 200, "branches export")
head = raw.decode().splitlines()[0].split(",")
accepted = schema_fields("BranchCreate")
c.ok(set(head) <= accepted, "every exported branch column is one the importer reads", sorted(set(head) - accepted))
c.ok({"code", "name", "address_line1", "currency_code", "status"} <= set(head), "the columns include code, name, address_line1, currency_code, status", head)
s, raw = a.raw(f"{WH}/export")
c.eq(s, 200, "warehouses export")
whead = raw.decode().splitlines()[0].split(",")
c.ok(set(whead) <= schema_fields("WarehouseCreate"), "every exported warehouse column is one the importer reads", sorted(set(whead) - schema_fields("WarehouseCreate")))
c.eq(whead[0], "branch_code", "the warehouse file names its branch by code, first")
first = raw.decode().splitlines()[1].split(",")[0]
c.ok(first != "", "the example names a branch by code", first)
br = by_code(a, BR, two()["branch_code"])
r = a.post(f"{WH}/import", {"records": [{"branch_code": br["code"], "code": f"WI{t}", "name": f"Imported warehouse {t}"}]})
c.ok(r[0] in (200, 201), "a warehouse imported by branch code", f"{r[0]} {message(r[1])}")
imp = [w for w in rows_of(a.get(f"{WH}?search=WI{t}")) if w["code"] == f"WI{t}"]
c.eq([w["branch_id"] for w in imp], [br["id"]], "it landed under that branch")
c.done()
