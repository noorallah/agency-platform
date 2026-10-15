"""Helpers the finance checks share (not a check; run.py skips it).

Re-uses the collections helpers (Scene, counter, bills, journals, trial
balance) and adds the finance ones. Firm ``one`` is a finished Wholesale firm
with its Firm admin, Viewer, Accountant and Cashier; firm ``two`` is a second
such firm. Money is compared as exact decimals.
"""

from __future__ import annotations

import pathlib
import sys
from decimal import Decimal
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "collections"))
sys.path.insert(0, str(HERE.parent / "buying"))

from _col import *  # noqa: E402,F401,F403
from _col import (  # noqa: E402,F401
    D, Api, Scene, by_code, counter, data, message, must, rows_of, today,
    suffix, journal_count, entry_by_id, entry_net, balanced,
)
import _buy  # noqa: E402,F401  (the buying chain: order, receipt, bill)
from common import client  # noqa: E402

buy = _buy
FIN = "/api/v1/finance"
JE = f"{FIN}/journal-entries"
PAY = "/api/v1/payments"
MODULE = "finance"


def admin(which: str = "admin") -> Api:
    """Return a signed-in account of the finance state."""
    return client(which, MODULE)


def period_of(api: Api, day: str | None = None) -> dict:
    """Return the accounting period holding a day (default today)."""
    day = day or today().isoformat()
    for p in rows_of(api.get(f"{FIN}/accounting-periods?page_size=100")):
        if p["starts_on"] <= day <= p["ends_on"]:
            return p
    raise SystemExit(f"PRECONDITION no accounting period holds {day}")


def account(api: Api, code: str) -> dict:
    """Return a ledger account by code."""
    return by_code(api, f"{FIN}/ledger-accounts", code)


def kinds(api: Api) -> tuple[str, str]:
    """Return (journal type id, voucher type id) for a manual journal."""
    j = rows_of(api.get(f"{FIN}/journal-types?page_size=100"))
    v = rows_of(api.get(f"{FIN}/voucher-types?page_size=100"))
    jt = next((x for x in j if x.get("code") in ("GENERAL", "GJ", "JV")), j[0])
    vt = next((x for x in v if x.get("code") in ("JOURNAL", "JV", "GENERAL")), v[0])
    return jt["id"], vt["id"]


def draft_body(
    api: Api, lines: list[tuple[str, str, str]], reference: str | None = None,
    day: str | None = None, period: dict | None = None,
) -> dict:
    """Body of a manual journal; lines are (account code, debit, credit)."""
    jt, vt = kinds(api)
    period = period or period_of(api, day)
    return {
        "journal_type_id": jt, "voucher_type_id": vt,
        "accounting_period_id": period["id"],
        "journal_date": day or today().isoformat(),
        "reference_number": reference or f"JV-MJ-{suffix(6)}",
        "description": "finance check",
        "lines": [
            {"ledger_account_id": account(api, code)["id"],
             "debit_amount": dr, "credit_amount": cr}
            for code, dr, cr in lines
        ],
    }


def tb(api: Api, period: dict | None = None) -> dict:
    """Return the trial balance report of a period."""
    period = period or period_of(api)
    return must(api.get(f"{FIN}/trial-balance?accounting_period_id={period['id']}"), "trial balance")


def tb_line(report: dict, code: str) -> dict:
    """Return one trial-balance line by account code."""
    zero = {"closing_debit": "0", "closing_credit": "0", "period_debit": "0", "period_credit": "0"}
    return next((x for x in report["lines"] if x["account_code"] == code), zero)


def closing(report: dict, code: str) -> Decimal:
    """Closing debit minus closing credit of an account in a trial balance."""
    line = tb_line(report, code)
    return D(line["closing_debit"]) - D(line["closing_credit"])


def sums(report: dict) -> tuple[Decimal, Decimal]:
    """Total closing debit and credit of a trial balance, added from the lines."""
    dr = sum((D(x["closing_debit"]) for x in report["lines"]), Decimal(0))
    cr = sum((D(x["closing_credit"]) for x in report["lines"]), Decimal(0))
    return dr, cr
