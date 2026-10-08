"""TC-MAST-024: an extra field is shown and required by goods type, customer group and supplier type."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from common import Check, client, data, message, suffix
from _lib import customer_body, field, goods_types, must, rule, vendor_body

c = Check("tc_mast_024")
tag = suffix()
admin, manager = client("admin"), client("manager")
types = goods_types(admin)
base = "/api/v1/business-framework"

shade = field(admin, f"SHADE_CODE_{tag}", "PRODUCT")
creg = field(admin, f"CONTRACTOR_REG_NO_{tag}", "CUSTOMER")
iec = field(admin, f"IMPORT_EXPORT_CODE_{tag}", "VENDOR")
cats = {}
for name, gt in (("EMULSIONS", "PAINT"), ("TABLETS", "MEDICINE"), ("SUNDRIES", None)):
    body = {"code": f"{name[:4]}{tag}", "name": f"{name} {tag}"}
    if gt:
        body["goods_type_id"] = types[gt]["id"]
    cats[name] = must(admin.post("/api/v1/products/categories", body), name)
contractors = must(admin.post("/api/v1/customers/groups",
                              {"code": f"CON{tag}", "name": f"Contractors {tag}"}), "group")
retailers = must(admin.post("/api/v1/customers/groups",
                            {"code": f"RET{tag}", "name": f"Retailers {tag}"}), "group")
importer = must(admin.post("/api/v1/vendors/types",
                           {"code": f"IMP{tag}", "name": f"Importer {tag}"}), "type")
local = must(admin.post("/api/v1/vendors/types",
                        {"code": f"LOC{tag}", "name": f"Local {tag}"}), "type")

r1 = rule(admin, shade["id"], goods_type_id=types["PAINT"]["id"], is_mandatory=False)
r2 = rule(admin, creg["id"], customer_group_id=contractors["id"], is_mandatory=True)
r3 = rule(admin, iec["id"], vendor_type_id=importer["id"], is_mandatory=True)
c.eq((r1[0], r2[0], r3[0]), (201, 201, 201), "the three rules are saved")

# (a) the product form's field list per category
def offered(cat: str) -> tuple[bool, bool]:
    s, b = admin.get(f"/api/v1/products/metadata?category_id={cats[cat]['id']}")
    d = data(b)
    return (shade["id"] in d["optional_attribute_definition_ids"],
            shade["id"] in d["required_attribute_definition_ids"])
c.eq(offered("EMULSIONS"), (True, False), "(a) Shade Code is offered for Emulsions, optional")
c.eq(offered("TABLETS"), (False, False), "(a) not offered for Tablets")
c.eq(offered("SUNDRIES"), (False, False), "(a) not offered for Sundries")

# (b) Contractors customer: refused empty, accepted with the number
b1 = admin.post("/api/v1/customers", customer_body(f"CB{tag}", customer_group_id=contractors["id"]))
c.refused(b1, 422, "Required attributes are missing", "(b) contractor without its registration number")
b2 = admin.post("/api/v1/customers", customer_body(
    f"CB{tag}", customer_group_id=contractors["id"],
    attributes=[{"attribute_definition_id": creg["id"], "value": "REG-1"}]))
c.eq(b2[0], 201, "(b) contractor with the number")
cust = data(b2[1]) if b2[0] == 201 else {}
c.eq([a.get("value_text") for a in cust.get("attributes", [])], ["REG-1"], "(b) the value reads back")

# (c) retailer and no group
c.eq(admin.post("/api/v1/customers", customer_body(f"CR{tag}", customer_group_id=retailers["id"]))[0],
     201, "(c) a retailer is accepted")
c.eq(admin.post("/api/v1/customers", customer_body(f"CN{tag}"))[0], 201, "(c) a customer in no group")
s, b = admin.get(f"{base}/attribute-definitions/applicable?entity_type=CUSTOMER")
rules = [k for k in data(b)["kind_rules"] if k["attribute_definition_id"] == creg["id"]]
c.eq([k["customer_group_id"] for k in rules], [contractors["id"]],
     "(c) the field is tied to Contractors only, so Retailers' form does not show it")

# (d) a retailer carrying the contractor field
d = admin.post("/api/v1/customers", customer_body(
    f"CD{tag}", customer_group_id=retailers["id"],
    attributes=[{"attribute_definition_id": creg["id"], "value": "X"}]))
c.refused(d, 422, "do not apply", "(d) a retailer carrying the contractor field")

# (e) move the contractor to Retailers, the form resubmitting what it still shows
if b2[0] == 201:
    e = admin.put(f"/api/v1/customers/{cust['id']}", customer_body(
        f"CB{tag}", customer_group_id=retailers["id"],
        attributes=[{"attribute_definition_id": creg["id"], "value": "REG-1"}]))
    c.eq(e[0], 200, "(e) moving the contractor to Retailers is accepted")
    s, b = admin.get(f"/api/v1/customers/{cust['id']}")
    c.eq([a.get("value_text") for a in data(b).get("attributes", [])], ["REG-1"],
         "(e) the registration number is still stored")

# (f) suppliers
f1 = admin.post("/api/v1/vendors", vendor_body(f"VI{tag}", type_id=importer["id"]))
c.refused(f1, 422, "Required attributes are missing", "(f) importer without the code")
f2 = admin.post("/api/v1/vendors", vendor_body(
    f"VI{tag}", type_id=importer["id"],
    attributes=[{"attribute_definition_id": iec["id"], "value": "IEC-9"}]))
c.eq(f2[0], 201, "(f) importer with the code")
f3 = admin.post("/api/v1/vendors", vendor_body(f"VL{tag}", type_id=local["id"]))
c.eq(f3[0], 201, "(f) a local supplier without it")

# (g) the same rule twice
c.refused(rule(admin, creg["id"], customer_group_id=contractors["id"], is_mandatory=True),
          409, "already exists", "(g) the Contractors rule a second time")

# (h) a product field naming a customer group
c.refused(rule(admin, shade["id"], customer_group_id=contractors["id"], is_mandatory=False),
          422, "", "(h) a product field cannot name a customer group")

# (i) a firm manager
s, b = admin.get(f"{base}/firm-custom-field-rules")
before = len(data(b))
i = rule(manager, shade["id"], category_code=f"TABL{tag}", is_mandatory=False)
c.eq(i[0], 403, "(i) the firm manager is refused")
s, b = admin.get(f"{base}/firm-custom-field-rules")
c.eq(len(data(b)), before, "(i) no rule was written")
c.done()
