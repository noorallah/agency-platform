"""Probe: a stale If-Match on a customer edit is refused 409; the current version is accepted; the version moves."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _mst import *
from _col import receipt

c = Check("p_mst_stale_version")
a = api()
d = described(a)
row = must(a.get(f"{CU}/{d['id']}"), "row")
v0 = row["version"]
body = echo("CustomerUpdate", row, {"addresses": "CustomerAddressInput", "contacts": "CustomerContactInput"}, notes="first")
ok = put_with(a, f"{CU}/{d['id']}", body, version=v0)
c.eq(ok[0], 200, f"the version just read is accepted ({message(ok[1])})")
v1 = must(a.get(f"{CU}/{d['id']}"), "row")["version"]
c.eq(v1 > v0, True, "the version moved")
stale = put_with(a, f"{CU}/{d['id']}", {**body, "notes": "second, from a stale read"}, version=v0)
c.ok(stale[0] == 409, "the old version is refused with 409", f"{stale[0]} {message(stale[1])}")
c.eq(must(a.get(f"{CU}/{d['id']}"), "row")["notes"], "first", "the stale write changed nothing")
star = put_with(a, f"{CU}/{d['id']}", {**body, "notes": "third"}, version=None)
c.eq(star[0], 200, "sending no If-Match is still accepted")
junk = a.call("PUT", f"{CU}/{d['id']}", body)
c.eq(junk[0], 200, "plain PUT without the header is accepted")
vend = full = vendor(a)
vrow = must(a.get(f"{VE}/{vend['id']}"), "vendor")
st = put_with(a, f"{VE}/{vend['id']}", {"code": vend["code"], "name": "renamed once"}, version=vrow["version"])
c.eq(st[0], 200, "vendor: current version accepted")
st = put_with(a, f"{VE}/{vend['id']}", {"code": vend["code"], "name": "renamed twice"}, version=vrow["version"])
c.eq(st[0], 409, "vendor: the same version again is stale, 409")
c.done()
