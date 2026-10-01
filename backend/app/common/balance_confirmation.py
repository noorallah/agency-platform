"""Balance confirmation letters for customers and suppliers (backlog 74 row 4).

At the year end an auditor asks the firm to write to its parties: "our books
show you owe us X as of 31 March; please confirm, or send your statement".
This draws that letter on the firm's letterhead, for one party or for every
party with a balance.

**The balance is the same arithmetic as the statement beside it**, so a letter
and the statement printed for the same day cannot disagree:

* A customer's is the sum of their receivable movements dated on or before the
  day -- what they owe less what they hold on account (``outstanding_delta``
  less ``advance_delta``), the customer statement's own source.
* A supplier's is what the payables ledger holds for them that day, traced
  through the documents that posted it (`SupplierStatementService`).

Positive means the usual direction (the customer owes the firm; the firm owes
the supplier); negative is an advance or a credit running the other way, and
the letter says which in words rather than printing a minus sign.
"""

from __future__ import annotations

import zipfile
from datetime import date
from decimal import Decimal
from enum import StrEnum
from io import BytesIO
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO, quantize_ledger
from app.customers.models import Customer, CustomerReceivableTransaction
from app.document_framework.services.letter_pdf import LetterPage, LetterPdfRenderer
from app.document_framework.services.print_support import (
    customer_party,
    firm_party,
    load_template,
)
from app.sales_invoice.services.invoice_pdf import PartyBlock, amount_in_words
from app.vendors.models import Vendor, VendorAddress
from app.vendors.services.statement_service import SupplierStatementService


class PartySide(StrEnum):
    """Whose balance the letter confirms."""

    CUSTOMER = "CUSTOMER"
    SUPPLIER = "SUPPLIER"


def _rupees(value: Decimal) -> str:
    """Write an amount with Indian digit grouping."""
    whole, _, paise = f"{abs(quantize_ledger(value)):.2f}".partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join([*groups, tail])
    return f"Rs. {whole}.{paise}"


def balance_sentence(side: PartySide, balance: Decimal, as_of: date) -> str:
    """Say in words who owes whom, and how much, on the day.

    Positive is the usual direction for the side; negative runs the other way
    -- a customer's advance, a supplier's credit to the firm.
    """
    day = as_of.strftime("%d-%m-%Y")
    if balance == ZERO:
        return (
            f"According to our books of account, there was no balance between "
            f"us as at {day}."
        )
    amount = f"{_rupees(balance)} ({amount_in_words(abs(balance))})"
    you_owe_us = (balance > ZERO) == (side is PartySide.CUSTOMER)
    if you_owe_us:
        return (
            f"According to our books of account, a sum of {amount} was due "
            f"from you to us as at {day}."
        )
    return (
        f"According to our books of account, a sum of {amount} was due from "
        f"us to you as at {day}."
    )


class BalanceConfirmationService:
    """Work out party balances on a day and draw the letters."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session

    # ---- balances ------------------------------------------------------

    def customer_balances(
        self, *, firm_id: UUID, as_of: date, customer_id: UUID | None = None
    ) -> dict[UUID, Decimal]:
        """Return each customer's net balance at the end of a day, grouped in SQL.

        Customers whose account nets to nothing are left out.
        """
        statement = (
            select(
                CustomerReceivableTransaction.customer_id,
                func.sum(
                    CustomerReceivableTransaction.outstanding_delta
                    - CustomerReceivableTransaction.advance_delta
                ),
            )
            .where(
                CustomerReceivableTransaction.firm_id == firm_id,
                CustomerReceivableTransaction.is_deleted.is_(False),
                CustomerReceivableTransaction.transaction_date <= as_of,
            )
            .group_by(CustomerReceivableTransaction.customer_id)
        )
        if customer_id is not None:
            statement = statement.where(
                CustomerReceivableTransaction.customer_id == customer_id
            )
        answer: dict[UUID, Decimal] = {}
        for owner, total in self._session.execute(statement).all():
            value = quantize_ledger(Decimal(str(total or 0)))
            if value != ZERO:
                answer[owner] = value
        return answer

    def supplier_balances(
        self, *, firm_id: UUID, as_of: date, vendor_id: UUID | None = None
    ) -> dict[UUID, Decimal]:
        """Return what the firm owed each supplier at the end of a day."""
        return SupplierStatementService(self._session).balances(
            firm_scope=firm_id, as_of=as_of, vendor_id=vendor_id
        )

    # ---- letters -------------------------------------------------------

    def letter(
        self, side: PartySide, party_id: UUID, *, firm_id: UUID, as_of: date
    ) -> tuple[bytes, str]:
        """Draw one party's letter, whatever the balance -- zero included.

        Raises:
            ResourceNotFoundError: If the party is not this firm's.

        """
        balances = (
            self.customer_balances(firm_id=firm_id, as_of=as_of, customer_id=party_id)
            if side is PartySide.CUSTOMER
            else self.supplier_balances(
                firm_id=firm_id, as_of=as_of, vendor_id=party_id
            )
        )
        code, page = self._page(
            side,
            party_id,
            balances.get(party_id, ZERO),
            firm_id=firm_id,
            as_of=as_of,
            firm=firm_party(firm_id),
        )
        pdf = LetterPdfRenderer(self._accent(firm_id)).render([page])
        return pdf, _file_name(code, as_of)

    def letters_for_everyone(
        self, side: PartySide, *, firm_id: UUID, as_of: date
    ) -> tuple[bytes, str, int]:
        """Draw a letter for every party with a balance, one PDF each, zipped.

        One file per party because each goes to a different address, by email
        or by post; a single combined PDF would have to be split by hand.

        Returns:
            The ZIP bytes, its file name, and how many letters it holds.

        Raises:
            ValidationError: If no party of that side has a balance that day.

        """
        balances = (
            self.customer_balances(firm_id=firm_id, as_of=as_of)
            if side is PartySide.CUSTOMER
            else self.supplier_balances(firm_id=firm_id, as_of=as_of)
        )
        who = "customer" if side is PartySide.CUSTOMER else "supplier"
        if not balances:
            raise ValidationError(
                f"No {who} had a balance on {as_of.strftime('%d-%m-%Y')}, so "
                "there is nothing to confirm."
            )
        firm = firm_party(firm_id)
        renderer = LetterPdfRenderer(self._accent(firm_id))
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for party_id, balance in sorted(
                balances.items(), key=lambda item: str(item[0])
            ):
                code, page = self._page(
                    side, party_id, balance, firm_id=firm_id, as_of=as_of, firm=firm
                )
                archive.writestr(_file_name(code, as_of), renderer.render([page]))
        name = f"balance-confirmations-{who}s-{as_of.isoformat()}.zip"
        return buffer.getvalue(), name, len(balances)

    def _accent(self, firm_id: UUID) -> str:
        """Return the firm's accent colour, as its invoices print it."""
        return load_template(
            self._session, firm_scope=firm_id, document_type="SALES_INVOICE"
        ).accent_color

    def _page(
        self,
        side: PartySide,
        party_id: UUID,
        balance: Decimal,
        *,
        firm_id: UUID,
        as_of: date,
        firm: PartyBlock,
    ) -> tuple[str, LetterPage]:
        """Lay out one party's letter. Returns the party code and the page."""
        code, addressee = (
            self._customer(party_id, firm_id=firm_id)
            if side is PartySide.CUSTOMER
            else self._supplier(party_id, firm_id=firm_id)
        )
        day = as_of.strftime("%d-%m-%Y")
        paragraphs = [
            "Dear Sir / Madam,",
            f"Sub: Confirmation of balance as at {day}",
            balance_sentence(side, balance, as_of),
            "Please confirm this balance by signing and returning a copy of "
            "this letter. If it does not agree with your books, please send us "
            f"your statement of our account up to {day} so that the difference "
            "can be reconciled.",
            "This letter is sent for the purpose of our annual audit. If we do "
            "not hear from you within 15 days, the balance will be taken as "
            "confirmed.",
            "We confirm the above balance  /  We do not agree; our books show "
            "Rs. ______________ (strike out whichever does not apply).",
        ]
        page = LetterPage(
            firm=firm,
            title="BALANCE CONFIRMATION",
            facts=[
                ("Date", utc_now().date().strftime("%d-%m-%Y")),
                ("Balance as at", day),
                ("Your account", f"{code} {addressee.name}"),
            ],
            addressee=addressee,
            paragraphs=paragraphs,
            counter_signatory=f"Signature and seal of {addressee.name}",
        )
        return code, page

    def _customer(self, customer_id: UUID, *, firm_id: UUID) -> tuple[str, PartyBlock]:
        """Return one customer's code and addressee block."""
        row = self._session.scalar(
            select(Customer).where(
                Customer.id == customer_id,
                Customer.firm_id == firm_id,
                Customer.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Customer not found.")
        block = customer_party(self._session, customer_id, "BILLING") or PartyBlock(
            name=row.display_name or row.name, address_lines=[]
        )
        return row.code, block

    def _supplier(self, vendor_id: UUID, *, firm_id: UUID) -> tuple[str, PartyBlock]:
        """Return one supplier's code and addressee block."""
        row = self._session.scalar(
            select(Vendor).where(
                Vendor.id == vendor_id,
                Vendor.firm_id == firm_id,
                Vendor.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Supplier not found.")
        address = self._session.scalar(
            select(VendorAddress)
            .where(
                VendorAddress.vendor_id == vendor_id,
                VendorAddress.is_deleted.is_(False),
            )
            .order_by(
                VendorAddress.is_primary.desc(),
                VendorAddress.created_at.asc(),
                VendorAddress.id.asc(),
            )
            .limit(1)
        )
        lines = (
            [part for part in (address.address_line1, address.address_line2) if part]
            if address is not None
            else []
        )
        return row.code, PartyBlock(
            name=row.display_name or row.name,
            address_lines=lines,
            gstin=row.gstin,
            pan=row.pan,
            contact=row.phone,
        )


def _file_name(code: str, as_of: date) -> str:
    """Name one letter's PDF after the party and the day."""
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in code)
    return f"balance-confirmation-{safe}-{as_of.isoformat()}.pdf"


__all__ = ["BalanceConfirmationService", "PartySide", "balance_sentence"]
