import sys, json
sys.path.insert(0, ".")
from _rcm import sign_in
st = json.load(open("state.json"))
a = sign_in(); a.firm = st["firm_id"]
BR, WH = "38bf5aff-cdc3-457a-ab79-c5363bf726ae", "50efacad-3d41-46fe-8b76-2cf31ab03952"
print(a.call("PUT", "/api/v1/purchases/workflow-settings", {"purchase_order_stage": False, "goods_receipt_stage": False, "default_branch_id": BR, "default_warehouse_id": WH})[0])
v = a.ok("POST", "/api/v1/vendors", {"code": "GTA-UNREG", "name": "Swift Roadways (unregistered GTA)", "gst_registration": False, "gst_registration_type": "UNREGISTERED"})
print("vendor", v["id"])
units = a.ok("GET", "/api/v1/uom-framework/uoms?page_size=100")
print([u["code"] for u in units][:30])
