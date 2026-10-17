"""Soak: five TEST01 users doing a mixed normal day at once, for N minutes.

    python docs/qa/checks/concurrency/setup.py --adopt CM SM ACC   # once
    python docs/qa/checks/concurrency/run_soak.py --soak 15
    python docs/qa/checks/concurrency/run_soak.py --soak 0.5       # smoke test

Item 30m, the soak. Five signed-in users (two Firm-admin desks, the Seller,
a manager and the Accountant) loop on their own threads, each picking from
what that role does in a day: sales orders made and approved, counter bills
made and approved, receipts against approved bills, purchase orders made,
approved and received, customer edits carrying ``If-Match``, stock reads,
list reads and the trial balance. Every call is counted per action as ok, a
named refusal (a 4xx that says why) or a 5xx (or a dropped call).

Afterwards: no 5xx; no unnamed 4xx; no document number repeated within a
series; no stock below zero; the trial balance of every period balanced.
Each failure prints one line and the script exits non-zero. It writes
nothing to the repository; the result is copied into the round's note.
"""

from __future__ import annotations

import argparse
import random
import sys
import threading
import time
from collections import Counter, defaultdict
from decimal import Decimal
from typing import Any

from run_concurrency import (
    CU,
    FIN,
    INV,
    RC,
    SETTING_KEYS,
    SETTINGS,
    SI,
    SO,
    Answer,
    CounterStages,
    Firm,
    D,
    all_rows,
    data,
    message,
    must,
    put_if_match,
    rows_of,
    suffix,
    today,
)

PO = "/api/v1/purchases"
GR = "/api/v1/goods-receipts"

#: Who does what in a day. Weights are relative.
DAY: dict[str, dict[str, int]] = {
    "admin": {"po_cycle": 3, "si_cycle": 3, "so_cycle": 2, "reads": 3, "stock": 2},
    "admin_b": {"po_cycle": 2, "si_cycle": 3, "so_cycle": 3, "edit": 3, "reports": 2},
    "seller": {"so_draft": 4, "si_draft": 3, "reads": 3},
    "manager": {"approve_pool": 5, "so_cycle": 2, "reads": 3},
    "accountant": {"receipt": 6, "reads": 3, "reports": 3},
}

NUMBER_KEYS = (
    "invoice_number",
    "order_number",
    "so_number",
    "po_number",
    "grn_number",
    "receipt_number",
    "settlement_number",
    "document_number",
    "number",
)


class Tally:
    """Count every call per action: ok, named refusal, 5xx, unnamed 4xx."""

    def __init__(self) -> None:
        """Start empty."""
        self.lock = threading.Lock()
        self.ok: Counter[str] = Counter()
        self.refused: Counter[str] = Counter()
        self.server: Counter[str] = Counter()
        self.unnamed: Counter[str] = Counter()
        self.denied: Counter[str] = Counter()
        self.reasons: dict[str, Counter[str]] = defaultdict(Counter)
        self.samples: list[str] = []

    def add(self, action: str, answer: Answer, what: str = "") -> Answer:
        """Classify one answer and return it."""
        status, body = answer
        with self.lock:
            if status in (200, 201, 204):
                self.ok[action] += 1
            elif status == 403:
                self.denied[action] += 1
            elif 400 <= status < 500:
                said = message(body).strip()
                if said:
                    self.refused[action] += 1
                    self.reasons[action][f"{status} {said[:70]}"] += 1
                else:
                    self.unnamed[action] += 1
                    self.samples.append(f"unnamed {status} {action} {what}")
            else:
                self.server[action] += 1
                self.samples.append(
                    f"{status} {action} {what}: {str(message(body) or body)[:200]}"
                )
        return answer


class Soak:
    """The five desks, the shared masters and the pools the desks pass along."""

    def __init__(self) -> None:
        """Sign in, make the shared masters and stock them."""
        self.firm = Firm()
        self.tally = Tally()
        self.lock = threading.Lock()
        self.tag = suffix(5)
        self.users = {name: self.firm.users[name] for name in DAY}
        self.products = [self.firm.product(f"{self.tag}{n}", "5000") for n in range(3)]
        self.customers = [self.firm.customer(f"{self.tag}{n}") for n in range(4)]
        self.vendor = must(
            self.firm.admin.post(
                "/api/v1/vendors",
                {"code": f"SV{self.tag}", "name": f"Soak vendor {self.tag}"},
            ),
            "vendor",
        )
        #: Documents made, by series, as (id, user).
        self.made: dict[str, list[str]] = defaultdict(list)
        self.draft_invoices: list[str] = []
        self.draft_orders: list[str] = []
        self.owing: list[tuple[str, str]] = []  # (invoice id, customer id)
        self.relogins = 0
        self.stop_at = 0.0

    # -- plumbing -----------------------------------------------------------
    def call(
        self,
        user: str,
        action: str,
        method: str,
        path: str,
        body: Any = None,  # noqa: ANN401
    ) -> Answer:
        """Make one call as a desk, counted under ``action``; sign in again on 401."""
        api = self.users[user]
        try:
            answer = api.call(method, path, body)
            if answer[0] == 401:
                fresh = self.firm_login(user)
                api.token = fresh.token
                answer = api.call(method, path, body)
        except Exception as error:  # noqa: BLE001
            answer = (-1, f"{type(error).__name__}: {error}")
        return self.tally.add(action, answer, f"{method} {path}")

    def firm_login(self, user: str) -> Any:  # noqa: ANN401
        """Sign the desk's account in again (token aged out)."""
        from common import client

        with self.lock:
            self.relogins += 1
        return client("admin" if user.startswith("admin") else user, "concurrency")

    def keep(self, series: str, answer: Answer) -> dict | None:
        """Remember a made document's id and return its data."""
        if answer[0] in (200, 201):
            row = data(answer[1])
            if isinstance(row, dict) and row.get("id"):
                with self.lock:
                    self.made[series].append(str(row["id"]))
                return row
        return None

    def pick(self, items: list) -> Any:  # noqa: ANN401
        """Return a random item."""
        return random.choice(items)

    # -- the day's actions ----------------------------------------------------
    def so_body(self) -> dict:
        """Return a sales order body of one to three pieces."""
        return {
            "customer_id": self.pick(self.customers)["id"],
            "order_date": today().isoformat(),
            "branch_id": self.firm.branch["id"],
            "warehouse_id": self.firm.warehouse["id"],
            "lines": [
                {
                    "line_number": 1,
                    "product_id": self.pick(self.products)["id"],
                    "quantity": str(random.randint(1, 3)),
                }
            ],
        }

    def so_draft(self, user: str) -> None:
        """Type a sales order and leave it for a manager."""
        row = self.keep("sales order", self.call(user, "so create", "POST", SO, self.so_body()))
        if row:
            with self.lock:
                self.draft_orders.append(row["id"])

    def so_cycle(self, user: str) -> None:
        """Type a sales order and approve it."""
        row = self.keep("sales order", self.call(user, "so create", "POST", SO, self.so_body()))
        if row:
            self.call(user, "so approve", "POST", f"{SO}/{row['id']}/approve", {})

    def si_body(self) -> dict:
        """Return a counter bill of one to three pieces."""
        body = self.firm.bill_body(self.pick(self.customers), self.pick(self.products))
        body["lines"][0]["current_invoice_quantity"] = str(random.randint(1, 3))
        return body

    def si_draft(self, user: str) -> None:
        """Type a counter bill and leave it for a manager."""
        row = self.keep("sales invoice", self.call(user, "si create", "POST", SI, self.si_body()))
        if row:
            with self.lock:
                self.draft_invoices.append(row["id"])

    def si_cycle(self, user: str) -> None:
        """Type a counter bill, approve it and note it as owing."""
        row = self.keep("sales invoice", self.call(user, "si create", "POST", SI, self.si_body()))
        if row:
            self.approve_invoice(user, row["id"], row["customer_id"])

    def approve_invoice(self, user: str, invoice_id: str, customer_id: str) -> None:
        """Approve a bill and, if it took, put it where receipts look."""
        status, _ = self.call(user, "si approve", "POST", f"{SI}/{invoice_id}/approve", {})
        if status == 200:
            with self.lock:
                self.owing.append((invoice_id, customer_id))

    def approve_pool(self, user: str) -> None:
        """Approve whatever the Seller left: a bill or an order."""
        with self.lock:
            bill = self.draft_invoices.pop() if self.draft_invoices else None
            order = self.draft_orders.pop() if self.draft_orders else None
        if bill:
            status, body = self.users[user].get(f"{SI}/{bill}")
            if status == 200:
                self.approve_invoice(user, bill, data(body)["customer_id"])
        if order:
            self.call(user, "so approve", "POST", f"{SO}/{order}/approve", {})

    def receipt(self, user: str) -> None:
        """Record a receipt, part or all of a bill's 118.00-a-piece value."""
        with self.lock:
            if not self.owing:
                return
            invoice_id, customer_id = self.pick(self.owing)
        amount = f"{random.choice([20, 50, 100, 118, 236]):.2f}"
        body = {
            "party_id": customer_id,
            "settlement_date": today().isoformat(),
            "amount": amount,
            "method": random.choice(["BANK", "CASH"]),
            "allocations": [{"invoice_id": invoice_id, "amount": amount}],
        }
        row = self.keep("receipt", self.call(user, "receipt create", "POST", RC, body))
        if row is None:
            return

    def po_cycle(self, user: str) -> None:
        """Order from the vendor, approve, receive in full and complete."""
        product = self.pick(self.products)
        qty = str(random.randint(5, 20))
        body = {
            "branch_id": self.firm.branch["id"],
            "warehouse_id": self.firm.warehouse["id"],
            "vendor_id": self.vendor["id"],
            "purchase_date": today().isoformat(),
            "lines": [
                {"product_id": product["id"], "ordered_quantity": qty, "unit_price": "60"}
            ],
        }
        order = self.keep("purchase order", self.call(user, "po create", "POST", PO, body))
        if not order:
            return
        for step in ("submit", "approve"):
            status, _ = self.call(user, f"po {step}", "POST", f"{PO}/{order['id']}/{step}", {})
            if status != 200:
                return
        status, got = self.users[user].get(f"{PO}/{order['id']}")
        if status != 200:
            return
        line = data(got)["lines"][0]
        grn = {
            "purchase_order_id": order["id"],
            "receipt_date": today().isoformat(),
            "lines": [
                {
                    "purchase_order_line_id": line["id"],
                    "line_number": 1,
                    "current_receipt_quantity": qty,
                    "free_quantity": "0",
                    "unit_price": "60",
                    "warehouse_id": self.firm.warehouse["id"],
                }
            ],
        }
        made = self.keep("goods receipt", self.call(user, "grn create", "POST", GR, grn))
        if made:
            self.call(user, "grn complete", "POST", f"{GR}/{made['id']}/complete", {})

    def edit(self, user: str) -> None:
        """Rename a shared customer carrying the version just read (If-Match)."""
        held = self.pick(self.customers)
        api = self.users[user]
        status, body = api.get(f"{CU}/{held['id']}")
        if status != 200:
            self.tally.add("customer read", (status, body))
            return
        read = data(body)
        save = {
            "code": read["code"],
            "name": f"Soak buyer {self.tag} by {user} {random.randint(0, 999)}",
            "customer_type": read["customer_type"],
            "currency_code": read["currency_code"],
        }
        self.tally.add(
            "customer edit (If-Match)",
            put_if_match(api, f"{CU}/{held['id']}", save, int(read["version"])),
            f"PUT {CU}/{held['id']}",
        )

    def reads(self, user: str) -> None:
        """Open lists the way a screen does."""
        path = random.choice(
            [
                f"{SI}?page_size=25&sort_by=created_at&sort_direction=desc",
                f"{SO}?page_size=25&sort_by=created_at&sort_direction=desc",
                f"{CU}?page_size=25",
                f"{RC}?page_size=25",
            ]
            if user != "admin" and user != "admin_b"
            else [
                f"{SI}?page_size=25&sort_by=created_at&sort_direction=desc",
                f"{SO}?page_size=25&sort_by=created_at&sort_direction=desc",
                f"{CU}?page_size=25",
                f"{RC}?page_size=25",
                f"{PO}?page_size=25",
                f"{GR}?page_size=25",
            ]
        )
        self.call(user, "list read", "GET", path)

    def stock(self, user: str) -> None:
        """Read on-hand for one of the soak items."""
        product = self.pick(self.products)
        self.call(user, "stock read", "GET", f"{INV}?product_id={product['id']}&page_size=25")

    def reports(self, user: str) -> None:
        """Read the trial balance of today's period, or the sales summary."""
        period = self.period_today()
        if period and random.random() < 0.7:
            self.call(
                user,
                "trial balance read",
                "GET",
                f"{FIN}/trial-balance?accounting_period_id={period['id']}",
            )
        else:
            self.call(user, "list read", "GET", f"{PO}/summary")

    def period_today(self) -> dict | None:
        """Return the accounting period holding today."""
        day = today().isoformat()
        status, body = self.firm.admin.get(f"{FIN}/accounting-periods?page_size=100")
        for row in (data(body) if status == 200 else []) or []:
            if row["starts_on"] <= day <= row["ends_on"]:
                return row
        return None

    # -- the loop -------------------------------------------------------------
    def desk(self, user: str) -> None:
        """Run one user's day until the clock runs out."""
        menu = DAY[user]
        names = list(menu)
        weights = list(menu.values())
        while time.monotonic() < self.stop_at:
            action = random.choices(names, weights)[0]
            try:
                getattr(self, action)(user)
            except Exception as error:  # noqa: BLE001
                self.tally.add(action, (-1, f"{type(error).__name__}: {error}"))
            time.sleep(random.uniform(0.2, 1.0))

    def run(self, minutes: float) -> None:
        """Start the five desks together and wait for them."""
        self.stop_at = time.monotonic() + minutes * 60
        threads = [threading.Thread(target=self.desk, args=(u,)) for u in DAY]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()


def number_of(row: dict) -> str | None:
    """Return the document number a row carries."""
    for key in NUMBER_KEYS:
        if row.get(key):
            return str(row[key])
    return None


READ = {
    "sales order": SO,
    "sales invoice": SI,
    "receipt": RC,
    "purchase order": PO,
    "goods receipt": GR,
}


def verify(soak: Soak) -> list[str]:
    """Return one line per failure of the after-checks, and print the facts."""
    problems: list[str] = []
    admin = soak.firm.admin
    t = soak.tally
    for action, count in sorted(t.server.items()):
        problems.append(f"{count} x 5xx or dropped call on '{action}'")
    for action, count in sorted(t.unnamed.items()):
        problems.append(f"{count} x 4xx with no message on '{action}'")
    problems.extend(t.samples[:20])

    print("\nDocument numbers (read back from the server)")
    for series, path in READ.items():
        ids = soak.made[series]
        numbers: list[str] = []
        blank = 0
        for doc_id in ids:
            status, body = admin.get(f"{path}/{doc_id}")
            row = data(body) if status == 200 else {}
            got = number_of(row) if isinstance(row, dict) else None
            if got:
                numbers.append(got)
            else:
                blank += 1
        repeated = [n for n, c in Counter(numbers).items() if c > 1]
        print(
            f"  {series}: {len(ids)} made, {len(numbers)} numbered, "
            f"{blank} without a number yet, {len(repeated)} repeated"
        )
        if repeated:
            problems.append(f"{series}: number repeated {repeated[:5]}")

    print("\nStock")
    rows = all_rows(admin, f"{INV}?include_deleted=false")
    negative = [
        r
        for r in rows
        if D(r["current_quantity"]) < 0 or D(r.get("reserved_quantity", 0)) < 0
    ]
    mine = {p["id"] for p in soak.products}
    for product in soak.products:
        have = sum(
            (D(r["current_quantity"]) for r in rows if r["product_id"] == product["id"]),
            Decimal(0),
        )
        print(f"  {product['code']}: on hand {have}")
    print(f"  {len(rows)} stock rows in the firm, {len(negative)} below zero")
    for r in negative[:10]:
        problems.append(
            f"stock below zero: product {r['product_id']} "
            f"{'(soak item)' if r['product_id'] in mine else ''} "
            f"on hand {r['current_quantity']}, reserved {r.get('reserved_quantity')}"
        )

    print("\nTrial balance")
    periods = rows_of(admin.get(f"{FIN}/accounting-periods?page_size=100"))
    checked = unbalanced = 0
    for period in periods:
        status, body = admin.get(
            f"{FIN}/trial-balance?accounting_period_id={period['id']}"
        )
        if status != 200:
            problems.append(f"trial balance {period['code']}: {status} {message(body)}")
            continue
        report = data(body)
        checked += 1
        debit, credit = D(report["total_debit"]), D(report["total_credit"])
        if debit != credit or not report["is_balanced"]:
            unbalanced += 1
            problems.append(
                f"trial balance {period['code']} not balanced: "
                f"debit {debit} credit {credit}"
            )
    print(f"  {checked} periods read, {unbalanced} unbalanced")
    return problems


def report(soak: Soak, minutes: float, started: float) -> None:
    """Print the per-action table."""
    t = soak.tally
    actions = sorted(set(t.ok) | set(t.refused) | set(t.server) | set(t.unnamed))
    print(f"\nSoak of {minutes} min, {time.monotonic() - started:.0f} s elapsed")
    print(f"{'action':28} {'ok':>6} {'refused':>8} {'5xx':>5} {'unnamed':>8}")
    for a in actions:
        print(f"{a:28} {t.ok[a]:>6} {t.refused[a]:>8} {t.server[a]:>5} {t.unnamed[a]:>8}")
    print(
        f"{'TOTAL':28} {sum(t.ok.values()):>6} {sum(t.refused.values()):>8} "
        f"{sum(t.server.values()):>5} {sum(t.unnamed.values()):>8}"
    )
    print("\nNamed refusals")
    for a in actions:
        for reason, n in t.reasons[a].most_common(6):
            print(f"  {a}: {n} x {reason}")
    print(f"\nRe-sign-ins after a 401: {soak.relogins}")


def main() -> None:
    """Run the soak and exit non-zero on any finding."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--soak", type=float, default=15.0, metavar="MINUTES")
    args = parser.parse_args()
    soak = Soak()
    settings = soak.firm.admin.get(SETTINGS)
    held = data(settings[1])
    base = {k: held[k] for k in SETTING_KEYS if k in held}
    print(f"tag {soak.tag}; stages off for the run, put back after")
    started = time.monotonic()
    try:
        with CounterStages(soak.firm.admin):
            soak.run(args.soak)
    finally:
        soak.firm.admin.put(SETTINGS, base)
    report(soak, args.soak, started)
    problems = verify(soak)
    print()
    for line in problems:
        print(f"FAIL {line}")
    print("ok: no finding" if not problems else f"{len(problems)} finding(s)")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
