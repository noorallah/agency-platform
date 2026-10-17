"""Activate the two RCM_GTA rules; make the service item, the transporter; stages off."""
import sys, json
sys.path.insert(0, ".")
from _rcm import sign_in
st = json.load(open("state.json"))
a = sign_in(); a.firm = st["firm_id"]
# 1. rules
rules = a.ok("GET", "/api/v1/tax-framework/rules?search=RCM_GTA&page_size=50")
for r in rules:
    if r["status"] == "ACTIVE":
        continue
    body = {k: r[k] for k in ("effective_from","effective_to","country_id","business_profile_id","tax_profile_id","code","name","description","priority") if k in r}
    body["status"] = "ACTIVE"
    body["conditions"] = [{k: c[k] for k in ("sequence","field_key","operator","value_text","value_number","value_date","value_boolean","value_json")} for c in r["conditions"]]
    body["actions"] = [{k: x[k] for k in ("sequence","action_type","target_tax_profile_id","target_tax_component_id","percentage_override","parameters")} for x in r["actions"]]
    print(r["code"], a.call("PUT", f"/api/v1/tax-framework/rules/{r['id']}", body)[0])
for r in a.ok("GET", "/api/v1/tax-framework/rules?search=RCM&page_size=50"):
    print(r["code"], r["status"], r["priority"])
# 2. workflow: stages off
w = a.ok("GET", "/api/v1/purchases/workflow-settings"); print(w)
