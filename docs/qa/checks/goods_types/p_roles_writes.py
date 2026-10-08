"""Probe: what the firm manager, sales manager and inventory manager get on every write route.

Expected from system_seed.py: goods types need CUSTOM_FIELD_MANAGE (firm administration: the
firm administrator only); unit sets need UOM_MANAGE (held by FIRM_MANAGER through the operational
groups, not by SALES_MANAGER or INVENTORY_MANAGER, who hold UOM_VIEW); product create, duplicate
and import need PRODUCT_CREATE / PRODUCT_IMPORT (FIRM_MANAGER yes; the other two hold PRODUCT_VIEW only).
"""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _gt import *  # noqa: F401,F403

c = Check("p_roles_writes")
tag = suffix()
admin = client("admin")
units = uom_ids(admin)
status, body = admin.post(GT, {"code": f"{tag}-R", "name": f"Roles {tag}"})
own_type = data(body)
status, body = admin.post(SETS, {"name": f"Roles set {tag}", "base_uom_id": units["PIECE"]})
own_set = data(body)
status, body = prod(admin, tag, "SRC")
src = data(body)
med = goods_type_by_code(admin, "MEDICINE")
cols = ["Code", "Name"]

for who, goods_ok, sets_ok, product_ok in (("manager", False, True, True), ("sales", False, False, False),
                                           ("store", False, False, False)):
    api = client(who)
    n = who.upper()
    got = {}
    got["goods type create"] = api.post(GT, {"code": f"{tag}-{n}", "name": f"By {who} {tag}"})[0]
    got["goods type update"] = api.put(f"{GT}/{own_type['id']}", {"name": f"By {who} {tag}"})[0]
    got["goods type use"] = api.put(f"{GT}/{med['id']}/use", {"in_use": True})[0]
    got["goods type delete"] = api.delete(f"{GT}/{own_type['id']}")[0]
    for name, status in got.items():
        c.eq(status in (200, 201, 204), goods_ok, f"{who}: {name} succeeded={status in (200, 201, 204)} (status {status})")
    # unit sets
    s_create, s_body = api.post(SETS, {"name": f"By {who} {tag}", "base_uom_id": units["PIECE"]})
    s_update = api.put(f"{SETS}/{own_set['id']}", {"description": f"by {who}"})[0]
    made = data(s_body) if s_create == 201 else None
    s_delete = api.delete(f"{SETS}/{made['id']}")[0] if made else 403
    for name, status in (("unit set create", s_create), ("unit set update", s_update), ("unit set delete", s_delete)):
        okay = status in (200, 201, 204)
        c.eq(okay, sets_ok, f"{who}: {name} succeeded={okay} (status {status})")
    # products
    p_create, p_body = prod(api, tag, f"P-{n}")
    p_dup = api.post(f"{PRODUCTS}/{src['id']}/duplicate")[0]
    code = f"{tag}-IMP-{n}"
    i_check = import_file(api, csv_bytes([{"Code": code, "Name": "Imported"}], cols))[0]
    i_apply = import_file(api, csv_bytes([{"Code": code, "Name": "Imported"}], cols), apply=True)[0]
    for name, status in (("product create", p_create), ("product duplicate", p_dup), ("import check", i_check),
                         ("import apply", i_apply)):
        okay = status in (200, 201)
        c.eq(okay, product_ok, f"{who}: {name} succeeded={okay} (status {status})")
    # every role reads
    c.eq(api.get(GT)[0], 200, f"{who}: reads goods types")
    c.eq(api.get(SETS)[0], 200, f"{who}: reads unit sets")
    print(f"  {who}: {got} sets=({s_create},{s_update},{s_delete}) products=({p_create},{p_dup},{i_check},{i_apply})")
admin.delete(f"{GT}/{own_type['id']}")
admin.delete(f"{SETS}/{own_set['id']}")
c.done()
