"""Helpers the reports checks share (not a check; run.py skips it).

The report table is read from the desktop catalogue itself, so it cannot drift
from the list the screen offers.
"""

from __future__ import annotations

import pathlib
import re
import sys
import time
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from common import Api, Check, client, data, message  # noqa: E402,F401

MODULE = "reports"
FROM, TO = "2025-04-01", "2026-12-31"
CATALOGUE = HERE.parents[3] / "desktop/lib/ui/reports/report_catalog.dart"
SLOW_MS = 3000
FY_ID = "5ac919cd-638f-4a63-bf4f-37a1de65ecbf"  # TEST01 FY2026
PRODUCT_ID = "00000000-0000-0000-0000-000000000000"  # replaced at run time


def admin() -> Api:
    """Sign in as the TEST01 admin."""
    return client("admin", MODULE)


def catalogue() -> list[dict[str, Any]]:
    """Return every catalogue entry: path and the flags that shape its query."""
    text = CATALOGUE.read_text(encoding="utf-8")
    out = []
    for chunk in text.split("ReportDefinition(")[1:]:
        m = re.search(r"path:\s*'([^']+)'", chunk)
        if not m:
            continue
        # Flags sit beside the path, before the columns list.
        head = chunk.split("columns:")[0]
        on = re.search(r"onDateParam:\s*'(\w+)'", head)
        days = re.search(r"\bdays:\s*(\d+)", head)
        out.append(
            {
                "path": m.group(1),
                "period": "needsPeriod: true" in head,
                "as_on": "asOnDate: true" in head,
                "on_param": on.group(1) if on else None,
                "days": days.group(1) if days else None,
                "quarterly": "quarterly: true" in head,
                "supplier": "needsSupplier: true" in head,
            }
        )
    return out


def first_id(api: Api, path: str) -> str | None:
    """Return the id of the first row of a list, or None."""
    status, body = api.get(f"{path}?page=1&page_size=1")
    rows = data(body) if status == 200 else []
    return str(rows[0]["id"]) if isinstance(rows, list) and rows else None


def query(entry: dict[str, Any], vendor_id: str | None) -> str:
    """Build the query string a report needs, the way the workspace does."""
    if entry["path"].endswith("it-block-schedule"):
        return f"?financial_year_id={FY_ID}"
    if entry["path"].endswith("rate-trend"):
        return f"?product_id={PRODUCT_ID}&from_date={FROM}&to_date={TO}"
    if entry["supplier"]:
        return f"?vendor_id={vendor_id}&from_date={FROM}&to_date={TO}"
    if entry["quarterly"]:
        return "?financial_year=2025-26&quarter=Q4&page=1&page_size=100"
    if entry["on_param"]:
        return f"?{entry['on_param']}={TO}"
    if entry["period"]:
        extra = f"&days={entry['days']}" if entry["days"] else ""
        return f"?from_date={FROM}&to_date={TO}{extra}&page=1&page_size=100"
    return f"?days={entry['days']}" if entry["days"] else ""


def read(api: Api, entry: dict[str, Any], vendor_id: str | None) -> tuple[int, Any, int]:
    """Read one report; return (status, body, milliseconds)."""
    global PRODUCT_ID
    if PRODUCT_ID.startswith("0000"):
        PRODUCT_ID = first_id(api, "/api/v1/products") or PRODUCT_ID
    started = time.perf_counter()
    status, body = api.get(entry["path"] + query(entry, vendor_id))
    return status, body, int((time.perf_counter() - started) * 1000)
