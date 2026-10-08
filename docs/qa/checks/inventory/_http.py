"""A request with extra headers (If-Match) the shared client does not send (not a check)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from common import BASE, Api


def call(
    api: Api,
    method: str,
    path: str,
    body: Any = None,
    *,
    if_match: str | None = None,
    firm: str | None = None,
    raw_headers: dict[str, str] | None = None,
) -> tuple[int, Any, dict[str, str]]:
    """Return (status, decoded body, response headers)."""
    headers = {"Content-Type": "application/json"}
    if api.token:
        headers["Authorization"] = f"Bearer {api.token}"
    fid = firm or api.firm_id
    if fid:
        headers["X-Firm-ID"] = fid
    if if_match is not None:
        headers["If-Match"] = if_match
    headers.update(raw_headers or {})
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            status, raw, hdr = r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        status, raw, hdr = e.code, e.read(), dict(e.headers)
    try:
        return status, json.loads(raw) if raw else None, hdr
    except ValueError:
        return status, raw, hdr
