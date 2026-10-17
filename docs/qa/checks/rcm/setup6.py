import sys, json
sys.path.insert(0, ".")
from _rcm import sign_in
st = json.load(open("state.json"))
a = sign_in(); a.firm = st["firm_id"]
C = "68a46517-1f77-45f8-a0ee-97c5774ef934"
TN, KA = "93ad22e1-6eb2-423f-ad8c-1da0503a7be0", "31e111f8-b2b7-4fb8-a280-ca8944eab774"
def vendor(code, name, state):
    f = [v for v in a.ok("GET", f"/api/v1/vendors?search={code}&page_size=10") if v["code"] == code]
    if f: return f[0]
    return a.ok("POST", "/api/v1/vendors", {"code": code, "name": name, "gst_registration": False, "gst_registration_type": "UNREGISTERED",
        "addresses": [{"address_type": "BILLING", "address_line1": "1 Transport Nagar", "country_id": C, "state_id": state, "is_primary": True}]})
st["vendor_local"] = vendor("GTA-TN", "Swift Roadways Tamil Nadu (unregistered GTA)", TN)["id"]
st["vendor_inter"] = vendor("GTA-KA", "Deccan Carriers Karnataka (unregistered GTA)", KA)["id"]
cos = a.ok("GET", "/api/v1/products/principals")
co = next((c for c in cos if c["code"] == "RCMCO"), None) or a.ok("POST", "/api/v1/products/principals", {"code": "RCMCO", "name": "RCM Company"})
brs = a.ok("GET", "/api/v1/products/brands")
br = next((b for b in brs if b["name"] == "RCM Brand"), None) or a.ok("POST", "/api/v1/products/brands", {"name": "RCM Brand", "principal_id": co["id"]})
profs = a.ok("GET", "/api/v1/tax-framework/profiles?search=RCM_GTA&page_size=10")
units = a.ok("GET", "/api/v1/uom-framework/uoms?page_size=100")
u = next(x["id"] for x in units if x["code"] == "EACH")
body = {"brand_id": br["id"], "code": "FREIGHT-GTA", "name": "Freight inward (GTA)", "product_type": "SERVICE", "tax_profile_group_code": "RCM_GTA_5",
        "hsn_sac": "996511", "purchase_price": "10000", "selling_price": "0",
        "base_uom_id": u, "inventory_uom_id": u, "sales_uom_id": u, "purchase_uom_id": u}
s, b = a.call("POST", "/api/v1/products", body)
print(s, str(b)[:600])
if s < 300: st["product"] = b["data"]["id"]
json.dump(st, open("state.json", "w"))
