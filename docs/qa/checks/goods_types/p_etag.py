"""Probe: version and ETag on a goods-type and a unit-set update."""
import json
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import urllib.error
import urllib.request

from _gt import *  # noqa: F401,F403
from common import BASE  # noqa: E402

c = Check("p_etag")
tag = suffix()
admin = client("admin")
units = uom_ids(admin)


def call(method, path, body=None, if_match=None):
    """Return (status, body, response headers) with an optional If-Match."""
    headers = {"Authorization": f"Bearer {admin.token}", "X-Firm-ID": admin.firm_id, "Content-Type": "application/json"}
    if if_match is not None:
        headers["If-Match"] = if_match
    request = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read() or b"null"), response.headers
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"null"), error.headers


for label, path, create, edit in (
    ("goods type", GT, {"code": f"{tag}-ET", "name": f"Etag {tag}"}, {"name": f"Etag renamed {tag}"}),
    ("unit set", SETS, {"name": f"Etag set {tag}", "base_uom_id": units["PIECE"]}, {"description": "changed"}),
):
    status, body, headers = call("POST", path, create)
    c.eq(status, 201, f"{label} created ({message(body)})")
    row = data(body)
    c.eq(headers.get("ETag"), f'"{row["version"]}"', f"{label}: create publishes the ETag")
    url = f"{path}/{row['id']}"
    status, body, headers = call("PUT", url, edit, if_match='"999"')
    c.eq(status, 409, f"{label}: a wrong If-Match is refused 409 (got {status} {message(body)})")
    status, body, headers = call("PUT", url, edit, if_match=f'"{row["version"]}"')
    c.eq(status, 200, f"{label}: the right If-Match saves ({message(body)})")
    after = data(body)
    c.eq(after["version"], row["version"] + 1, f"{label}: version moves by one")
    c.eq(headers.get("ETag"), f'"{after["version"]}"', f"{label}: update publishes the new ETag")
    status, body, headers = call("PUT", url, edit, if_match=f'"{row["version"]}"')
    c.eq(status, 409, f"{label}: the stale tag is refused 409 the second time")
    status, body, headers = call("PUT", url, edit)
    c.eq(status, 200, f"{label}: sending nothing is accepted")
    c.eq(data(body)["version"], after["version"], f"{label}: a save that changes nothing does not move the counter")
    status, body, headers = call("PUT", url, edit, if_match="banana")
    c.ok(status in (400, 422, 428, 409), f"{label}: a malformed If-Match is a client error, not a 500", status)
    call("DELETE", url)
c.done()
