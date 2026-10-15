"""Probe: a stale version on a role, user or template update."""
import json

from _ur import *

c = Check("p_ur_stale_version"); sc = Scene()


def put_with(a, method, path, body, etag):
    """Send JSON with an If-Match header, which Api cannot send."""
    head = {"Content-Type": "application/json", "Authorization": f"Bearer {a.token}", "X-Firm-ID": a.firm_id or "", "If-Match": etag}
    st, raw = fetch(method, path, json.dumps(body).encode(), head)
    return st, (json.loads(raw.decode()) if raw else None)


def etag_of(a, path):
    """Return the ETag a GET publishes (None when it publishes none)."""
    head = {"Authorization": f"Bearer {a.token}", "X-Firm-ID": a.firm_id or ""}
    import http.client, urllib.parse
    base = urllib.parse.urlsplit(__import__("common").BASE)
    conn = http.client.HTTPConnection(base.hostname, base.port, timeout=60)
    conn.request("GET", path, headers=head)
    r = conn.getresponse(); r.read(); out = r.getheader("ETag"); conn.close()
    return out


try:
    a = sc.admin
    role = sc.role(a)
    user = sc.user("stale")
    tpl = sc.new_template(a, [sc.role_id("CASHIER")])
    for what, path, body in (("role", f"{R}/{role['id']}", {"name": "Fresh"}),
                             ("user", f"{U}/{user['id']}", {"full_name": "Fresh"}),
                             ("template", f"{T}/{tpl['id']}", {"name": "Fresh"})):
        tag_ = etag_of(a, path)
        if tag_ is None:
            c.ok(False, f"{what}: GET publishes an ETag (no version precondition is possible without one)")
            continue
        st, _ = put_with(a, "PATCH", path, body, '"999"')
        c.ok(st in (409, 412), f"{what}: a stale If-Match is refused", st)
        st, _ = put_with(a, "PATCH", path, body, tag_)
        c.eq(st, 200, f"{what}: the ETag it was given is accepted")
finally:
    sc.cleanup()
c.done()
