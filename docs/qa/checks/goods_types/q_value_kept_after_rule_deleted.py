"""Probe: a value is kept when the rule that tied its field to a group is deleted."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from common import Check, client, data, suffix
from _lib import customer_body, field, must, rule

c = Check("q_value_kept_after_rule_deleted")
tag = suffix()
admin = client("admin")
BF = "/api/v1/business-framework"
creg = field(admin, f"KREG_{tag}", "CUSTOMER")
grp = must(admin.post("/api/v1/customers/groups", {"code": f"KG{tag}", "name": f"K {tag}"}), "group")
other = must(admin.post("/api/v1/customers/groups", {"code": f"KO{tag}", "name": f"O {tag}"}), "group")
r = rule(admin, creg["id"], customer_group_id=grp["id"], is_mandatory=True)
c.eq(r[0], 201, "rule saved")
attrs = [{"attribute_definition_id": creg["id"], "value": "KEEP-1"}]
cust = must(admin.post("/api/v1/customers", customer_body(
    f"KC{tag}", customer_group_id=grp["id"], attributes=attrs)), "customer")


def held() -> list:
    """The customer's stored values."""
    return [a.get("value_text") for a in data(admin.get(f"/api/v1/customers/{cust['id']}")[1])["attributes"]]


c.eq(held(), ["KEEP-1"], "the value is stored")
c.eq(admin.delete(f"{BF}/firm-custom-field-rules/{data(r[1])['id']}")[0], 204, "rule deleted")
c.eq(held(), ["KEEP-1"], "the value is kept after the rule is deleted")
# with the rule gone the field is untied: every customer is offered it, none is forced to fill it
s, b = admin.get(f"{BF}/attribute-definitions/applicable?entity_type=CUSTOMER")
c.ok(creg["id"] in [d["id"] for d in data(b)["definitions"]], "the field is offered to all customers now")
c.ok(creg["id"] not in data(b)["mandatory_ids"], "and is not compulsory")
plain = admin.post("/api/v1/customers", customer_body(f"KD{tag}", customer_group_id=other["id"]))
c.eq(plain[0], 201, "a customer in another group saves without it")
resave = admin.put(f"/api/v1/customers/{cust['id']}", customer_body(
    f"KC{tag}", customer_group_id=grp["id"], attributes=attrs))
c.eq(resave[0], 200, "the original customer re-saves with its value")
c.eq(held(), ["KEEP-1"], "and it is still there")
c.done()
