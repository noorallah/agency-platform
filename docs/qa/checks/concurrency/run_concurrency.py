"""Fire the same action from several TEST01 users at once at the running backend.

    python docs/qa/checks/concurrency/setup.py --adopt CM SM ACC   # once
    python docs/qa/checks/concurrency/run_concurrency.py           # every scenario
    python docs/qa/checks/concurrency/run_concurrency.py --only b  # one alone

Item 30m, part 1. The guards are proved at database level by the integration
suite; this proves them through HTTP with real sessions racing. Each scenario
makes its own records under a fresh tag, releases its calls together through a
barrier, and asserts: exactly one winner where only one may win, every loser
refused with a 4xx and a message (never a 500), no document number repeated.

    a  five bills approved at once take numbers from one series: none repeated
    b  four receipts of 100.00 against one 118.00 bill: one accepted
    c  one order approved by three users at once: one winner, stock reserved once
    d  one customer saved by three users with the same If-Match: one 200

Exits non-zero when any scenario fails; prints one line per finding.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import threading
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import (  # noqa: E402
    Api,
    all_rows,
    check_brand,
    client,
    data,
    fetch,
    message,
    suffix,
)

MODULE = "concurrency"
SO = "/api/v1/sales-orders"
SI = "/api/v1/sales-invoices"
RC = "/api/v1/receipts"
CU = "/api/v1/customers"
INV = "/api/v1/inventory"
SETTINGS = f"{SO}/workflow-settings"
SETTING_KEYS = (
    "quotation_stage",
    "sales_order_stage",
    "delivery_note_stage",
    "default_branch_id",
    "default_warehouse_id",
    "promotion_mode",
    "max_line_discount_percent",
    "rate_includes_tax",
    "new_outlets_need_approval",
    "reservation_lapse_days",
    "sales_order_approval",
    "delivery_note_approval",
    "sales_invoice_approval",
    "round_bills_to_rupee",
    "salesman_required",
    "box_and_piece_entry",
)

Answer = tuple[int, Any]


def today() -> date:
    """Return the firm's business day (India), as the server judges it."""
    return (datetime.now(UTC) + timedelta(hours=5, minutes=30)).date()


def D(value: object) -> Decimal:  # noqa: N802
    """Return a Decimal from whatever the server sent."""
    return Decimal(str(value if value is not None else 0))


def must(answer: Answer, what: str) -> Any:  # noqa: ANN401
    """Return the data of a 2xx answer or stop saying what was refused."""
    status, body = answer
    if status not in (200, 201):
        raise SystemExit(f"PRECONDITION {what}: {status} {message(body)}")
    return data(body)


def rows_of(answer: Answer) -> list[Any]:
    """Return the list of a list answer, or stop."""
    got = must(answer, "list")
    return got if isinstance(got, list) else []


def by_code(api: Api, path: str, code: str) -> dict:
    """Return the row with this code from a list."""
    for row in rows_of(api.get(f"{path}?search={code}&page_size=100")):
        if row.get("code") == code:
            return row
    raise SystemExit(f"PRECONDITION no {code} at {path}")


def put_if_match(api: Api, path: str, body: dict, version: int) -> Answer:
    """PUT JSON carrying ``If-Match``, which the common client cannot send."""
    headers = {"Content-Type": "application/json", "If-Match": f'"{version}"'}
    if api.token:
        headers["Authorization"] = f"Bearer {api.token}"
    if api.firm_id:
        headers["X-Firm-ID"] = api.firm_id
    status, raw = fetch("PUT", path, json.dumps(body).encode("utf-8"), headers)
    try:
        return status, json.loads(raw.decode("utf-8")) if raw else None
    except ValueError:
        return status, raw


def race(calls: list[Callable[[], Answer]]) -> list[Answer]:
    """Run the calls on threads released together; return answers in order."""
    gate = threading.Barrier(len(calls))
    answers: list[Answer] = [(0, None)] * len(calls)

    def run(n: int, call: Callable[[], Answer]) -> None:
        """Wait at the gate, then make one call and keep its answer."""
        gate.wait()
        try:
            answers[n] = call()
        except Exception as error:  # noqa: BLE001
            answers[n] = (-1, f"{type(error).__name__}: {error}")

    threads = [threading.Thread(target=run, args=(n, c)) for n, c in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return answers


class Result:
    """One scenario's findings."""

    def __init__(self, name: str, what: str) -> None:
        """Start an empty result."""
        self.name = name
        self.what = what
        self.failures: list[str] = []
        self.notes: list[str] = []

    def ok(self, condition: bool, what: str, got: object = None) -> None:
        """Record a failure when the condition does not hold."""
        if not condition:
            tail = "" if got is None else f" (got {str(got)[:400]})"
            self.failures.append(f"{what}{tail}")

    def note(self, text: str) -> None:
        """Record what was seen."""
        self.notes.append(text)


def summarise(answers: list[Answer]) -> str:
    """Return each answer as status plus the first words of its message."""
    parts = []
    for status, body in answers:
        said = "" if status in (200, 201) else f" '{message(body)[:90]}'"
        parts.append(f"{status}{said}")
    return "; ".join(parts)


def judge_one_winner(res: Result, answers: list[Answer]) -> None:
    """Assert one 2xx and every other answer a 4xx carrying a message."""
    wins = [a for a in answers if a[0] in (200, 201)]
    res.ok(len(wins) == 1, "exactly one call wins", summarise(answers))
    no_server_errors(res, answers)
    unfit = [a for a in answers if a[0] in (401, 403, 404)]
    res.ok(not unfit, "no caller is refused for who they are", summarise(unfit))
    for status, body in answers:
        if status not in (200, 201) and 400 <= status < 500:
            res.ok(bool(message(body).strip()), f"a {status} refusal names a reason")


def no_server_errors(res: Result, answers: list[Answer]) -> None:
    """Assert nothing answered 5xx or failed to answer."""
    bad = [a for a in answers if a[0] >= 500 or a[0] < 100]
    res.ok(not bad, "no call answers 5xx or drops", summarise(bad))


class Firm:
    """The TEST01 users and the firm's branch, warehouse and piece unit."""

    def __init__(self) -> None:
        """Sign every account in once."""
        self.users = {
            name: client(name, MODULE)
            for name in ("admin", "seller", "manager", "accountant")
        }
        # A second session of the admin: another desk signed in as the same person.
        self.users["admin_b"] = client("admin", MODULE)
        self.admin = self.users["admin"]
        self.branch = by_code(self.admin, "/api/v1/branches", "HO")
        self.warehouse = by_code(self.admin, "/api/v1/warehouses", "MAIN")
        self.piece = next(
            u["id"]
            for u in rows_of(self.admin.get("/api/v1/uom-framework/uoms?page_size=100"))
            if u["code"] == "PIECE"
        )

    def product(self, tag: str, stock: str = "500") -> dict:
        """Make a 100.00 item at 18% with stock in MAIN."""
        api = self.admin
        made = must(
            api.post(
                "/api/v1/products",
                {
                    "code": f"CC{tag}",
                    "name": f"Concurrency check item {tag}",
                    "brand_id": check_brand(api),
                    "product_type": "STOCK_ITEM",
                    "tax_profile_group_code": "GST_18_LOCAL",
                    "selling_price": "100",
                    "purchase_price": "60",
                    "base_uom_id": self.piece,
                    "inventory_uom_id": self.piece,
                    "sales_uom_id": self.piece,
                    "purchase_uom_id": self.piece,
                },
            ),
            "product",
        )
        stocked = must(
            api.post(
                f"{INV}/opening-stock",
                {
                    "branch_id": self.branch["id"],
                    "warehouse_id": self.warehouse["id"],
                    "reference_number": f"OS-CC{tag}",
                    "posting_date": today().isoformat(),
                    "lines": [
                        {"product_id": made["id"], "quantity": stock, "unit_cost": "60"}
                    ],
                },
            ),
            "opening stock",
        )
        must(api.post(f"{INV}/opening-stock/{stocked['id']}/post", {}), "post stock")
        return made

    def customer(self, tag: str) -> dict:
        """Make a business customer."""
        return must(
            self.admin.post(
                CU,
                {
                    "code": f"CC{tag}{suffix(3)}",
                    "name": f"Concurrency buyer {tag}",
                    "customer_type": "BUSINESS",
                    "currency_code": "INR",
                },
            ),
            "customer",
        )

    def bill_body(self, customer: dict, product: dict) -> dict:
        """Return a one-piece counter bill body (118.00)."""
        return {
            "customer_id": customer["id"],
            "branch_id": self.branch["id"],
            "invoice_date": today().isoformat(),
            "lines": [
                {
                    "line_number": 1,
                    "product_id": product["id"],
                    "current_invoice_quantity": "1",
                    "warehouse_id": self.warehouse["id"],
                }
            ],
        }

    def counter(self) -> CounterStages:
        """Return a context with the order and note stages off."""
        return CounterStages(self.admin)


class CounterStages:
    """Turn the order and note stages off for a block, then put them back."""

    def __init__(self, api: Api) -> None:
        """Hold the API to change settings with."""
        self.api = api
        self.base: dict[str, Any] = {}

    def __enter__(self) -> None:
        """Save the settings and switch the stages off."""
        held = must(self.api.get(SETTINGS), "workflow settings")
        self.base = {k: held[k] for k in SETTING_KEYS if k in held}
        wanted = {**self.base, "sales_order_stage": False, "delivery_note_stage": False}
        must(self.api.put(SETTINGS, wanted), "settings changed")

    def __exit__(self, *_: object) -> None:
        """Put the settings back."""
        must(self.api.put(SETTINGS, self.base), "settings put back")


def scenario_a(firm: Firm) -> Result:
    """Five bills drafted and approved at once: no number repeated."""
    res = Result("a", "5 bills from 4 users, drafted then approved at once")
    tag = suffix(5)
    product = firm.product(tag)
    buyer = firm.customer(tag)
    makers = ["admin", "seller", "manager", "admin_b", "seller"]
    # The Seller may type a bill but not approve one (SALES_APPROVE).
    approvers = ["admin", "manager", "admin_b", "admin", "manager"]
    with firm.counter():
        drafted = race(
            [
                (lambda u=u: firm.users[u].post(SI, firm.bill_body(buyer, product)))
                for u in makers
            ]
        )
        no_server_errors(res, drafted)
        made = [data(b) for s, b in drafted if s in (200, 201)]
        res.ok(len(made) == len(makers), "every draft is accepted", summarise(drafted))
        res.note(f"drafts at once: {summarise(drafted)}")
        # Topped up one at a time, so the approvals still race five bills.
        while len(made) < len(makers):
            made.append(
                must(firm.admin.post(SI, firm.bill_body(buyer, product)), "bill")
            )
        approved = race(
            [
                (lambda u=u, m=m: firm.users[u].post(f"{SI}/{m['id']}/approve", {}))
                for u, m in zip(approvers, made, strict=False)
            ]
        )
    no_server_errors(res, approved)
    res.ok(
        all(s == 200 for s, _ in approved),
        "every approval is accepted",
        summarise(approved),
    )
    numbers = [
        str(must(firm.admin.get(f"{SI}/{m['id']}"), "bill read")["invoice_number"])
        for m in made
    ]
    res.ok(len(set(numbers)) == len(numbers), "no bill number repeated", numbers)
    res.note(f"approvals at once: {summarise(approved)}")
    res.note(f"numbers {', '.join(sorted(numbers))}")
    return res


def scenario_b(firm: Firm) -> Result:
    """Four receipts of 100.00 against one 118.00 bill: one accepted."""
    res = Result("b", "4 receipts of 100.00 from 3 users against one 118.00 bill")
    tag = suffix(5)
    product = firm.product(tag)
    buyer = firm.customer(tag)
    with firm.counter():
        bill = must(firm.admin.post(SI, firm.bill_body(buyer, product)), "bill")
        must(firm.admin.post(f"{SI}/{bill['id']}/approve", {}), "bill approve")
    payers = ["admin", "accountant", "admin_b", "accountant"]

    def pay(user: str) -> Callable[[], Answer]:
        """Return one receipt of 100.00 set against the bill."""
        body = {
            "party_id": buyer["id"],
            "settlement_date": today().isoformat(),
            "amount": "100.00",
            "method": "BANK",
            "allocations": [{"invoice_id": bill["id"], "amount": "100.00"}],
        }
        return lambda: firm.users[user].post(RC, body)

    answers = race([pay(u) for u in payers])
    judge_one_winner(res, answers)
    rows = rows_of(firm.admin.get(f"{RC}/outstanding?customer_id={buyer['id']}"))
    left = next(
        (D(r["outstanding_amount"]) for r in rows if r["invoice_id"] == bill["id"]),
        Decimal(0),
    )
    res.ok(left == D("18.00"), "the bill owes 18.00 afterwards", left)
    res.note(f"answers {summarise(answers)}; bill owes {left}")
    return res


def scenario_c(firm: Firm) -> Result:
    """One order approved by three users at once: one winner, reserved once."""
    res = Result("c", "1 order approved by 3 users at once")
    tag = suffix(5)
    product = firm.product(tag)
    buyer = firm.customer(tag)
    order = must(
        firm.admin.post(
            SO,
            {
                "customer_id": buyer["id"],
                "order_date": today().isoformat(),
                "branch_id": firm.branch["id"],
                "warehouse_id": firm.warehouse["id"],
                "lines": [
                    {"line_number": 1, "product_id": product["id"], "quantity": "7"}
                ],
            },
        ),
        "order",
    )
    approvers = ["admin", "manager", "admin_b"]
    answers = race(
        [
            (lambda u=u: firm.users[u].post(f"{SO}/{order['id']}/approve", {}))
            for u in approvers
        ]
    )
    judge_one_winner(res, answers)
    rows = all_rows(firm.admin, f"{INV}?product_id={product['id']}")
    reserved = sum((D(r["reserved_quantity"]) for r in rows), Decimal(0))
    res.ok(reserved == D("7"), "7 pieces reserved once, not per approval", reserved)
    res.note(f"answers {summarise(answers)}; reserved {reserved}")
    return res


def scenario_d(firm: Firm) -> Result:
    """One customer saved by three users with one If-Match: one 200."""
    res = Result("d", "1 customer saved by 3 users with the same If-Match")
    held = firm.customer(suffix(5))
    read = must(firm.admin.get(f"{CU}/{held['id']}"), "customer read")
    version = int(read["version"])
    editors = ["admin", "manager", "admin_b"]

    def save(n: int, user: str) -> Callable[[], Answer]:
        """Return one save renaming the customer."""
        body = {
            "code": read["code"],
            "name": f"{read['name']} by {user}{n}",
            "customer_type": read["customer_type"],
            "currency_code": read["currency_code"],
        }
        return lambda: put_if_match(
            firm.users[user], f"{CU}/{held['id']}", body, version
        )

    answers = race([save(n, u) for n, u in enumerate(editors)])
    judge_one_winner(res, answers)
    losers = [s for s, _ in answers if s not in (200, 201)]
    res.ok(all(s == 409 for s in losers), "every loser is a 409", losers)
    after = must(firm.admin.get(f"{CU}/{held['id']}"), "customer reread")
    res.ok(
        int(after["version"]) == version + 1, "the version moved once", after["version"]
    )
    res.note(f"answers {summarise(answers)}; version {version} -> {after['version']}")
    return res


SCENARIOS: dict[str, Callable[[Firm], Result]] = {
    "a": scenario_a,
    "b": scenario_b,
    "c": scenario_c,
    "d": scenario_d,
}


def main() -> None:
    """Run the chosen scenarios and exit non-zero on any failure."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", choices=sorted(SCENARIOS), action="append")
    args = parser.parse_args()
    firm = Firm()
    failed = False
    for key in args.only or sorted(SCENARIOS):
        res = SCENARIOS[key](firm)
        verdict = "FAIL" if res.failures else "ok"
        print(f"{verdict} {res.name}: {res.what}")
        for line in res.notes:
            print(f"    {line}")
        for line in res.failures:
            print(f"    FAIL {line}")
        failed = failed or bool(res.failures)
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
