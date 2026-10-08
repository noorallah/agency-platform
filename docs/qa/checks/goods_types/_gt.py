"""Helpers the goods-type checks share (backlog 89). Not a check itself."""

from __future__ import annotations

import csv
import io
import pathlib
import sys
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import Api, Check, all_rows, client, data, message, state, suffix  # noqa: E402,F401

PRODUCTS = "/api/v1/products"
GT = "/api/v1/products/goods-types"
SETS = "/api/v1/uom-framework/unit-sets"


def firm_ids() -> dict[str, str]:
    """Return the fixture firms' ids by code."""
    return dict(state()["firms"])


def uom_ids(api: Api) -> dict[str, str]:
    """Return the unit catalogue by code."""
    return {row["code"]: row["id"] for row in all_rows(api, "/api/v1/uom-framework/uoms")}


def shared_types(api: Api) -> dict[str, dict[str, Any]]:
    """Return the shared goods types by code."""
    status, body = api.get(GT)
    return {r["code"]: r for r in data(body) if r["firm_id"] is None}


def goods_type_by_code(api: Api, code: str) -> dict[str, Any]:
    """Return one goods type (shared or own) by its code."""
    status, body = api.get(GT)
    return next(r for r in data(body) if r["code"] == code)


def ensure_use(
    api: Api,
    code: str,
    *,
    hsn: str | None = "KEEP",
    group: str | None = "KEEP",
) -> dict[str, Any]:
    """Put a shared type in use (idempotent); defaults only when given."""
    row = goods_type_by_code(api, code)
    body: dict[str, Any] = {"in_use": True}
    if hsn != "KEEP":
        body["default_hsn_sac"] = hsn
    if group != "KEEP":
        body["default_tax_profile_group_code"] = group
    status, answer = api.put(f"{GT}/{row['id']}/use", body)
    if status != 200:
        raise SystemExit(f"cannot put {code} in use: {status} {message(answer)}")
    return data(answer)


def make_category(
    api: Api,
    tag: str,
    name: str,
    *,
    goods_type_id: str | None = None,
    parent_id: str | None = None,
) -> tuple[int, Any]:
    """Create a category carrying a goods type."""
    body: dict[str, Any] = {"code": f"{tag}-{name}".upper(), "name": f"{name} {tag}"}
    if goods_type_id is not None:
        body["goods_type_id"] = goods_type_id
    if parent_id is not None:
        body["parent_id"] = parent_id
    return api.post(f"{PRODUCTS}/categories", body)


def cat(api: Api, tag: str, name: str, **kw: Any) -> dict[str, Any]:
    """Create a category or stop the check."""
    status, body = make_category(api, tag, name, **kw)
    if status not in (200, 201):
        raise SystemExit(f"category {name}: {status} {message(body)}")
    return data(body)


def product_body(tag: str, name: str, **extra: Any) -> dict[str, Any]:
    """Return a minimal product payload with a code under the tag."""
    body: dict[str, Any] = {
        "code": f"{tag}-{name}".upper(),
        "name": f"{name} {tag}",
        "product_type": "STOCK_ITEM",
    }
    body.update(extra)
    return body


def prod(api: Api, tag: str, name: str, **extra: Any) -> tuple[int, Any]:
    """Create a product."""
    return api.post(PRODUCTS, product_body(tag, name, **extra))


def get_product(api: Api, product_id: str) -> dict[str, Any]:
    """Read one product back."""
    status, body = api.get(f"{PRODUCTS}/{product_id}")
    return data(body)


def csv_bytes(rows: list[dict[str, str]], columns: list[str]) -> bytes:
    """Build an import CSV with exactly these columns."""
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: row.get(c, "") for c in columns})
    return out.getvalue().encode("utf-8")


def import_file(
    api: Api,
    content: bytes,
    *,
    apply: bool = False,
    name: str = "p.csv",
    existing: str = "refuse",
) -> tuple[int, Any]:
    """Check (or apply) a product file."""
    return api.upload(
        f"{PRODUCTS}/import-file",
        name,
        content,
        fields={"apply": "true" if apply else "false", "existing": existing},
    )


def issues_text(body: Any) -> str:
    """Return the report's issues and warnings as one searchable string."""
    d = data(body)
    if not isinstance(d, dict):
        return str(body)[:400]
    items = list(d.get("issues", [])) + list(d.get("warnings", []))
    return " | ".join(i.get("text", "") for i in items)


def audit_actions(api: Api, entity_type: str, entity_id: str) -> list[str]:
    """Return the audit actions recorded for one entity (this firm's trail)."""
    rows = all_rows(
        api, f"/api/v1/audit-logs?entity_type={entity_type}&entity_id={entity_id}"
    )
    return [str(r.get("action")) for r in rows]
