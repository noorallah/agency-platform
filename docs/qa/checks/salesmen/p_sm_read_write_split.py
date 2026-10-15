"""Probe: a plain member reads the salesman list; writing needs SALESMAN_MANAGE."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sm import *

c = Check("p_sm_read_write_split")
a = admin()
mine = Scene(a, stock="").salesman()
for who_ in ("viewer", "exec"):
    api = admin(who_)
    c.eq(api.get(f"{SM}?page_size=5")[0], 200, f"{who_} reads the list")
    c.eq(api.get(f"{SM}/{mine['id']}")[0], 200, f"{who_} reads one")
    c.eq(api.get(f"{SM}/starting-choice")[0], 200, f"{who_} reads the starting choice")
    c.eq(api.post(SM, {"name": f"Nope {suffix(5)}"})[0], 403, f"{who_} cannot add")
    c.eq(api.put(f"{SM}/{mine['id']}", {"phone": "123"})[0], 403, f"{who_} cannot edit")
    c.eq(api.delete(f"{SM}/{mine['id']}")[0], 403, f"{who_} cannot delete")
    c.eq(api.post(f"{SM}/{mine['id']}/restore", {})[0], 403, f"{who_} cannot restore")
c.eq(Api().get(SM)[0], 401, "no sign-in is refused")
status, body = a.get(f"{SM}/{mine['id']}")
c.eq(data(body).get("phone"), None, "the refused edit changed nothing")
c.done()
