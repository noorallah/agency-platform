"""Helpers the Settings-section checks share (not a check; run.py skips it).

Two firms: ``ready`` (a finished firm: books open, GST template applied, head
office, Wholesale profile; its Firm admin and a Viewer) and ``bare`` (provisioned
only: nothing set up; a Firm admin made by setup). ``plat`` is a platform admin.
"""

from __future__ import annotations

import pathlib
import sys
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import (  # noqa: E402,F401
    PASSWORD,
    Api,
    Check,
    all_rows,
    client,
    data,
    message,
    save_state,
    sign_in,
    state,
    suffix,
)

AUDIT = "/api/v1/audit-logs"


def must(answer: tuple[int, Any], what: str) -> Any:  # noqa: ANN401
    """Return the data of a 2xx answer or stop saying what was refused."""
    status, body = answer
    if status not in (200, 201):
        raise SystemExit(f"PRECONDITION {what}: {status} {message(body)}")
    return data(body)


def rows_of(answer: tuple[int, Any]) -> list[Any]:
    """Return the list of a list answer, or stop."""
    got = must(answer, "list")
    return got if isinstance(got, list) else []


def who(account: str, firm: str | None = None) -> Api:
    """Sign in as an account, acting inside ``firm`` ('ready'/'bare') if named."""
    held = state()
    api = client(account)
    if firm:
        api.firm_id = held[f"{firm}_id"]
    return api


def section(api: Api, name: str) -> tuple[int, Any]:
    """GET one section's state."""
    return api.get(f"/api/v1/settings-sections/{name}/state")


def steps(api: Api, name: str) -> dict[str, tuple[str, str]]:
    """Return {step code: (state, detail)} for a section, in a dict that keeps order."""
    status, body = section(api, name)
    if status != 200:
        raise SystemExit(f"PRECONDITION section {name}: {status} {message(body)}")
    return {s["code"]: (s["state"], s["detail"]) for s in data(body)["steps"]}


def order_ok(c: Check, got: dict, expected: list[str], what: str) -> None:
    """Check the steps come in the documented order."""
    c.eq(list(got), expected, f"{what} step order")


def audit_count(api: Api) -> int:
    """Return the total of the firm's audit trail."""
    status, body = api.get(f"{AUDIT}?page=1&page_size=1")
    if status != 200:
        raise SystemExit(f"PRECONDITION audit read: {status} {message(body)}")
    return int(body["pagination"]["total_records"])


# --------------------------------------------------------------------------
# The documented order of every section (desktop/docs/DESKTOP_FRAMEWORK.md).
# --------------------------------------------------------------------------
ORDER: dict[str, list[str]] = {
    "tax": [
        "rates-and-profiles", "tax-rules", "tax-settings", "gst-documents",
        "tds-purchases",
    ],
    "firm": [
        "firm-profile", "financial-years", "numbering-series", "bill-series",
        "goods-types",
        "custom-fields", "custom-field-rules", "messaging", "approval-levels",
    ],
    "selling": [
        "sales-stages", "salesmen", "credit-control", "price-floor",
        "discount-limits", "loyalty-scheme", "tcs",
    ],
    "buying": ["purchase-settings", "approval-limits", "purchase-budgets"],
    "stock": [
        "adjustment-reasons", "adjustment-limits", "batch-rules", "costing-method",
    ],
    "business-profile": [
        "profile-assignment", "feature-management", "module-configuration",
        "attribute-definitions", "mandatory-attributes", "unit-sets",
    ],
    "pricing": ["price-lists", "price-levels", "promotions", "loyalty"],
    "territories": ["territories", "route-types", "route-builder", "transporters"],
    "account-structure": ["control-accounts", "cost-centers", "profit-centers"],
    "party-lists": [
        "customer-groups", "vendor-categories", "vendor-types", "licence-types",
        "licence-check-settings",
    ],
    "item-lists": [
        "uoms", "uom-groups", "conversion-rules", "packaging-types",
        "packaging-levels", "product-categories", "principals", "brands",
    ],
    "locations": [
        "geography-masters", "branch-types", "warehouse-types", "storage-areas",
    ],
    "platform/people": ["roles", "user-templates", "users", "user-firms"],
    "platform/firms": ["business-profiles", "firms"],
}

#: The only steps the table lets be To do (and the condition is data-tied).
MAY_BE_TODO = {
    "tax": {"rates-and-profiles", "tax-rules"},
    "firm": {"financial-years"},
    "selling": {"salesmen"},
    "account-structure": {"control-accounts", "cost-centers", "profit-centers"},
    "item-lists": {"uoms"},
    "platform/people": {"roles", "users"},
    "platform/firms": {"firms"},
}


def norm(value: Any) -> str:  # noqa: ANN401
    """Return a comparable form: numbers by value, so 5 equals 5.000."""
    from decimal import Decimal, InvalidOperation

    if isinstance(value, (bool, type(None))):
        return str(value)
    try:
        return str(Decimal(str(value)).normalize())
    except InvalidOperation:
        return str(value)


def lead(detail: str) -> int:
    """Return the first whole number in a detail, 0 for 'None yet'."""
    import re

    found = re.search(r"\d+", detail)
    return int(found.group()) if found else 0


def count_of(detail: str, word: str) -> int:
    """Return the number written before ``word`` in a detail, 0 when absent."""
    import re

    found = re.search(rf"(\d+) {word}", detail)
    return int(found.group(1)) if found else 0


def state_of(api: Api, name: str) -> dict:
    """Return the whole state document of a section (or stop)."""
    path = (
        f"/api/v1/settings-sections/{name}/state"
        if not name.startswith("platform/")
        else f"/api/v1/settings-sections/{name.replace('/', '/', 1)}/state"
    )
    status, body = api.get(path)
    if status != 200:
        raise SystemExit(f"PRECONDITION state {name}: {status} {message(body)}")
    return data(body)


def shape(c: Check, api: Api, name: str, who_: str) -> dict[str, tuple[str, str]]:
    """Read a section and check its shape: order, states, to-do count, details."""
    doc = state_of(api, name)
    got = {s["code"]: (s["state"], s["detail"]) for s in doc["steps"]}
    c.eq(doc.get("section"), name.split("/")[-1], f"{who_} {name}: section echoed")
    c.eq(list(got), ORDER[name], f"{who_} {name}: steps in the documented order")
    c.eq(
        doc.get("todo_count"),
        sum(1 for s, _ in got.values() if s == "TODO"),
        f"{who_} {name}: todo_count equals the TODO rows",
    )
    allowed = MAY_BE_TODO.get(name, set())
    for code, (st, detail) in got.items():
        c.ok(st in ("DONE", "TODO", "OPTIONAL"), f"{name}/{code} state word", st)
        c.ok(bool(detail), f"{name}/{code} has a detail line", detail)
        if st == "TODO":
            c.ok(code in allowed, f"{name}/{code} is To do but the table lets only "
                 f"{sorted(allowed)} be", st)
    return got


_OPENAPI: dict | None = None


def put_fields(path: str) -> list[str]:
    """Return the property names the PUT of a path accepts (from /openapi.json)."""
    global _OPENAPI
    if _OPENAPI is None:
        _OPENAPI = data(Api().get("/openapi.json")[1]) or {}
    spec = _OPENAPI["paths"][path]["put"]["requestBody"]["content"]["application/json"]
    ref = spec["schema"]["$ref"].split("/")[-1]
    return list(_OPENAPI["components"]["schemas"][ref]["properties"])


def singleton(
    c: Check,
    api: Api,
    path: str,
    section_: str,
    step: str,
    flip: tuple[str, Any] | None = None,
    detail_for: Any = None,
    admin_for_state: Api | None = None,
) -> None:
    """Read a settings screen, put it back unchanged, change one value, restore.

    Each leg is read back, and the step it belongs to is read again.
    ``detail_for(body)`` says what the step should read for a given body.
    """
    reader = admin_for_state or api
    tag = f"{path}"
    status, body = api.get(path)
    if not c.eq(status, 200, f"GET {tag}"):
        return
    keys = put_fields(path)
    original = {k: v for k, v in data(body).items() if k in keys}

    def put(values: dict) -> bool:
        got, answer = api.put(path, values)
        return c.eq(got, 200, f"PUT {tag} {message(answer)[:120]}")

    def readback(values: dict, what: str) -> None:
        got, answer = api.get(path)
        if got != 200:
            c.eq(got, 200, f"GET {tag} {what}")
            return
        now = data(answer)
        for key, value in values.items():
            c.eq(norm(now.get(key)), norm(value), f"{tag} {what}: {key} read back")

    def step_says(values: dict, what: str) -> None:
        if detail_for is None:
            return
        want = detail_for(values)
        got_state = steps(reader, section_)
        c.eq(got_state[step][1], want, f"{section_}/{step} {what}")

    if not put(original):
        return
    readback(original, "after the same body is put back")
    step_says(original, "after saving unchanged")
    key, value = flip if flip else (None, None)
    if key is None:
        for k, v in original.items():
            if isinstance(v, bool):
                key, value = k, (not v)
                break
    if key is None:
        return
    changed = {**original, key: value}
    if put(changed):
        readback({key: value}, f"after changing {key}")
        step_says(changed, f"after {key}={value}")
    if put(original):
        readback({key: original[key]}, f"after putting {key} back")
        step_says(original, f"after {key} put back")


def grow(
    c: Check,
    api: Api,
    section_: str,
    step: str,
    path: str,
    body: dict,
    word: str | None = None,
) -> dict | None:
    """Create one record through its own endpoint and check the step counts it.

    The step's leading number (or the number before ``word``) must rise by one.
    """
    before = steps(api, section_)[step][1]
    if "name" in body and not path.endswith("/salesmen"):
        body = {**body, "name": f"{body['name']} {suffix(4)}"}  # names are unique
    status, answer = api.post(path, body)
    if not c.ok(status in (200, 201), f"POST {path} saves", f"{status} {message(answer)[:200]}"):
        return None
    after = steps(api, section_)[step][1]
    pick = (lambda d: count_of(d, word)) if word else lead
    c.eq(pick(after), pick(before) + 1, f"{section_}/{step}: {before!r} -> {after!r}")
    return data(answer)


def total(api: Api, path: str) -> int:
    """Return the total_records of a list endpoint."""
    status, body = api.get(f"{path}{'&' if '?' in path else '?'}page=1&page_size=1")
    if status != 200:
        raise SystemExit(f"PRECONDITION list {path}: {status} {message(body)}")
    return int((body.get("pagination") or {}).get("total_records", len(data(body))))


def limits_flow(
    c: Check, api: Api, section_: str, step: str, path: str, role: str, field_: str
) -> None:
    """Replace a firm's role-limit list with one more role, then put it back.

    The list endpoints are PUT-replace, so the step must read one more role
    limit with the extra row and the original count once it is put back.
    """
    status, body = api.get(path)
    if not c.eq(status, 200, f"GET {path}"):
        return
    rows = data(body)
    rows = rows.get("limits", rows) if isinstance(rows, dict) else rows
    keep = [{"role_code": r["role_code"], field_: r[field_]} for r in rows]
    before = steps(api, section_)[step][1]
    c.eq(lead(before), len(keep), f"{section_}/{step} counts the {len(keep)} limits held")
    extra = [r for r in keep if r["role_code"] != role] + [
        {"role_code": role, field_: "10"}
    ]
    got, answer = api.put(path, {"limits": extra})
    if c.eq(got, 200, f"PUT {path} {message(answer)[:150]}"):
        c.eq(lead(steps(api, section_)[step][1]), len(extra),
             f"{section_}/{step} after adding {role}")
    got, answer = api.put(path, {"limits": keep})
    if c.eq(got, 200, f"PUT {path} back {message(answer)[:150]}"):
        c.eq(lead(steps(api, section_)[step][1]), len(keep),
             f"{section_}/{step} after putting the list back")
