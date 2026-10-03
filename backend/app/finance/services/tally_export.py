"""Export the books to Tally (MSG-5, decision A135).

Many firms' accountants keep the books in TallyPrime. This writes the
firm's posted journals for a period in Tally's XML import format, so the CA
imports them rather than re-typing a month of bills:

* **Masters** -- a ledger for every account the period's vouchers use, and
  a ledger per customer and supplier, with its GSTIN and state, under
  *Sundry Debtors* / *Sundry Creditors*. An account is named and grouped as
  the firm's mapping says; with no mapping, under its own name in the group
  its type and purpose suggest (bank and cash accounts, duties and taxes,
  sales and purchase accounts, current assets and liabilities, direct and
  indirect income and expenses).
* **Vouchers** -- one per posted journal, typed by where it came from (a
  sales invoice is a *Sales* voucher, a receipt a *Receipt*, a supplier's
  bill a *Purchase*, notes *Credit Note* / *Debit Note*, a contra a
  *Contra*, anything else a *Journal*), each line a ledger entry. A line on
  the receivable or payable control account names the party of the
  document behind it, so the CA's party ledgers carry the balances.

Tally reads a debit as a negative amount with ``ISDEEMEDPOSITIVE`` Yes. GST
travels as the tax ledgers the journals post to, and the party's GSTIN on its
ledger.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID
from xml.sax.saxutils import escape, quoteattr

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ValidationError
from app.core.utils.dates import utc_now
from app.finance.models import (
    FirmControlAccount,
    JournalEntry,
    JournalLine,
    LedgerAccount,
)
from app.finance.models.tally import TallyLedgerMapping
from app.finance.services.control_accounts import ControlAccountPurpose

ZERO = Decimal("0")

#: The voucher type a journal's source becomes in Tally.
VOUCHER_TYPES: dict[str, str] = {
    "sales_invoice": "Sales",
    "purchase_invoice": "Purchase",
    "credit_note": "Credit Note",
    "sales_return": "Credit Note",
    "customer_debit_note": "Debit Note",
    "debit_note": "Debit Note",
    "purchase_return": "Debit Note",
    "contra": "Contra",
}

#: Where a document's party is, by the module that posted its journal.
_PARTIES: dict[str, str] = {
    "sales_invoice": "app.sales_invoice.models:SalesInvoice",
    "credit_note": "app.credit_note.models:CreditNote",
    "customer_debit_note": "app.customer_debit_note.models:CustomerDebitNote",
    "sales_return": "app.sales_return.models:SalesReturn",
    "purchase_invoice": "app.purchase_invoice.models:PurchaseInvoice",
    "purchase_return": "app.purchase_return.models:PurchaseReturn",
    "debit_note": "app.debit_note.models:DebitNote",
    "settlements": "app.settlements.models:Settlement",
    "party_adjustments": "app.party_adjustments.models:PartyAdjustment",
}

#: Tally's group for an account the firm uses for one of these purposes.
_GROUP_BY_PURPOSE: dict[str, str] = {
    ControlAccountPurpose.CASH.value: "Cash-in-Hand",
    ControlAccountPurpose.BANK.value: "Bank Accounts",
    ControlAccountPurpose.ACCOUNTS_RECEIVABLE.value: "Sundry Debtors",
    ControlAccountPurpose.ACCOUNTS_PAYABLE.value: "Sundry Creditors",
    ControlAccountPurpose.SALES_REVENUE.value: "Sales Accounts",
    ControlAccountPurpose.SALES_RETURNS.value: "Sales Accounts",
    ControlAccountPurpose.PURCHASE_EXPENSE.value: "Purchase Accounts",
    ControlAccountPurpose.PURCHASE_RETURNS.value: "Purchase Accounts",
    ControlAccountPurpose.INVENTORY.value: "Stock-in-Hand",
}

#: Tally's group by account type, when no purpose decides it.
_GROUP_BY_TYPE: dict[str, str] = {
    "ASSET": "Current Assets",
    "LIABILITY": "Current Liabilities",
    "INCOME": "Indirect Incomes",
    "EXPENSE": "Indirect Expenses",
    "EQUITY": "Capital Account",
}


class TallyMappingWrite(BaseModel):
    """One account's name and group in the CA's Tally."""

    model_config = ConfigDict(extra="forbid")

    ledger_account_id: UUID
    tally_name: str = Field(min_length=1, max_length=200)
    tally_parent: str | None = Field(default=None, max_length=200)


class TallyMappingsWrite(BaseModel):
    """Every mapping, replacing what is there."""

    model_config = ConfigDict(extra="forbid")

    mappings: list[TallyMappingWrite] = Field(default_factory=list, max_length=2000)


class TallyMappingResponse(BaseModel):
    """One account, and what it is called and grouped as in Tally."""

    model_config = ConfigDict(extra="forbid")

    ledger_account_id: UUID
    account_code: str
    account_name: str
    tally_name: str
    tally_parent: str
    mapped: bool


@dataclass(frozen=True)
class _Ledger:
    """A ledger as it is exported."""

    name: str
    parent: str
    gstin: str | None = None
    state: str | None = None


class TallyExportService:
    """Name the firm's ledgers for Tally and export a period of vouchers."""

    def __init__(self, session: Session) -> None:
        """Bind to the caller's session."""
        self._session = session

    # ---- the mapping ---------------------------------------------------

    def mappings(self, firm_id: UUID) -> list[TallyMappingResponse]:
        """Return every account with its Tally name and group."""
        accounts = self._accounts(firm_id)
        names = self._account_ledgers(firm_id, accounts)
        mapped = self._mapped(firm_id)
        return [
            TallyMappingResponse(
                ledger_account_id=account.id,
                account_code=account.code,
                account_name=account.name,
                tally_name=names[account.id].name,
                tally_parent=names[account.id].parent,
                mapped=account.id in mapped,
            )
            for account in accounts.values()
        ]

    def replace_mappings(
        self, firm_id: UUID, data: TallyMappingsWrite, *, actor_id: UUID
    ) -> list[TallyMappingResponse]:
        """Replace the firm's mapping; commit.

        Raises:
            ValidationError: If an account is not the firm's, is named twice,
                or two accounts would share one Tally name.

        """
        accounts = self._accounts(firm_id)
        ids = [item.ledger_account_id for item in data.mappings]
        if len(set(ids)) != len(ids):
            raise ValidationError("An account is mapped twice.")
        if set(ids) - set(accounts):
            raise ValidationError("An account is not one of this firm's.")
        names = [item.tally_name.strip().lower() for item in data.mappings]
        if len(set(names)) != len(names):
            raise ValidationError("Two accounts cannot share one Tally ledger name.")
        now = utc_now()
        for row in self._session.scalars(
            select(TallyLedgerMapping).where(
                TallyLedgerMapping.firm_id == firm_id,
                TallyLedgerMapping.is_deleted.is_(False),
            )
        ).all():
            row.is_deleted = True
            row.deleted_at = now
            row.deleted_by = actor_id
        self._session.flush()
        for item in data.mappings:
            self._session.add(
                TallyLedgerMapping(
                    firm_id=firm_id,
                    ledger_account_id=item.ledger_account_id,
                    tally_name=item.tally_name.strip(),
                    tally_parent=(item.tally_parent or "").strip() or None,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        record_audit(
            self._session,
            action="tally.mappings_replaced",
            entity_type="tally_ledger_mappings",
            entity_id=firm_id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"count": len(data.mappings)},
        )
        self._session.commit()
        return self.mappings(firm_id)

    # ---- the export ----------------------------------------------------

    def export(self, firm_id: UUID, *, from_date: date, to_date: date) -> bytes:
        """Return the period's masters and vouchers as Tally import XML.

        Raises:
            ValidationError: If the period runs backwards.

        """
        if to_date < from_date:
            raise ValidationError("The period ends before it starts.")
        entries = list(
            self._session.scalars(
                select(JournalEntry)
                .where(
                    JournalEntry.firm_id == firm_id,
                    JournalEntry.is_deleted.is_(False),
                    JournalEntry.status == "POSTED",
                    JournalEntry.journal_date >= from_date,
                    JournalEntry.journal_date <= to_date,
                )
                .order_by(
                    JournalEntry.journal_date,
                    JournalEntry.reference_number,
                    JournalEntry.id,
                )
            ).all()
        )
        lines = (
            list(
                self._session.scalars(
                    select(JournalLine)
                    .where(
                        JournalLine.journal_entry_id.in_([e.id for e in entries]),
                        JournalLine.is_deleted.is_(False),
                    )
                    .order_by(JournalLine.journal_entry_id, JournalLine.line_number)
                ).all()
            )
            if entries
            else []
        )
        accounts = self._accounts(firm_id)
        ledgers = self._account_ledgers(firm_id, accounts)
        party_accounts = self._party_accounts(firm_id)
        parties = self._parties(entries)
        party_ledgers = self._party_ledgers(set(parties.values()))
        used: dict[str, _Ledger] = {}
        vouchers: list[str] = []
        by_entry: dict[UUID, list[JournalLine]] = {}
        for line in lines:
            by_entry.setdefault(line.journal_entry_id, []).append(line)
        for entry in entries:
            party = parties.get(entry.id)
            party_ledger = party_ledgers.get(party) if party else None
            rows: list[tuple[_Ledger, Decimal]] = []
            for line in by_entry.get(entry.id, []):
                ledger = ledgers.get(line.ledger_account_id)
                if ledger is None:
                    continue
                if line.ledger_account_id in party_accounts and party_ledger:
                    ledger = party_ledger
                amount = Decimal(str(line.credit_amount or 0)) - Decimal(
                    str(line.debit_amount or 0)
                )
                if amount == ZERO:
                    continue
                rows.append((ledger, amount))
                used[ledger.name] = ledger
            if rows:
                vouchers.append(self._voucher(entry, rows, party_ledger))
        company = FirmMetadataReader(self._session).get(firm_id).name or ""
        return _envelope(
            company, [self._master(ledger) for ledger in used.values()], vouchers
        )

    # ---- helpers -------------------------------------------------------

    def _accounts(self, firm_id: UUID) -> dict[UUID, LedgerAccount]:
        """Return the firm's live accounts by id, in code order."""
        return {
            account.id: account
            for account in self._session.scalars(
                select(LedgerAccount)
                .where(
                    LedgerAccount.firm_id == firm_id,
                    LedgerAccount.is_deleted.is_(False),
                )
                .order_by(LedgerAccount.code)
            ).all()
        }

    def _mapped(self, firm_id: UUID) -> dict[UUID, TallyLedgerMapping]:
        """Return the firm's live mappings by account."""
        return {
            row.ledger_account_id: row
            for row in self._session.scalars(
                select(TallyLedgerMapping).where(
                    TallyLedgerMapping.firm_id == firm_id,
                    TallyLedgerMapping.is_deleted.is_(False),
                )
            ).all()
        }

    def _account_ledgers(
        self, firm_id: UUID, accounts: dict[UUID, LedgerAccount]
    ) -> dict[UUID, _Ledger]:
        """Name and group every account as Tally will see it."""
        mapped = self._mapped(firm_id)
        purposes: dict[UUID, str] = {}
        for account_id, purpose in self._session.execute(
            select(FirmControlAccount.ledger_account_id, FirmControlAccount.purpose)
            .where(
                FirmControlAccount.firm_id == firm_id,
                FirmControlAccount.is_deleted.is_(False),
            )
            .order_by(FirmControlAccount.purpose)
        ).all():
            purposes.setdefault(account_id, purpose)
        answer: dict[UUID, _Ledger] = {}
        for account in accounts.values():
            row = mapped.get(account.id)
            purpose = purposes.get(account.id, "")
            default_parent = _GROUP_BY_PURPOSE.get(purpose) or (
                "Duties & Taxes"
                if "TAX" in purpose or "TDS" in purpose or "TCS" in purpose
                else _GROUP_BY_TYPE.get(account.account_type, "Suspense A/c")
            )
            answer[account.id] = _Ledger(
                name=row.tally_name if row else account.name,
                parent=(
                    row.tally_parent if row and row.tally_parent else default_parent
                ),
            )
        return answer

    def _party_accounts(self, firm_id: UUID) -> set[UUID]:
        """Return the receivable and payable control accounts."""
        return set(
            self._session.scalars(
                select(FirmControlAccount.ledger_account_id).where(
                    FirmControlAccount.firm_id == firm_id,
                    FirmControlAccount.is_deleted.is_(False),
                    FirmControlAccount.purpose.in_(
                        [
                            ControlAccountPurpose.ACCOUNTS_RECEIVABLE.value,
                            ControlAccountPurpose.ACCOUNTS_PAYABLE.value,
                        ]
                    ),
                )
            ).all()
        )

    def _parties(self, entries: Iterable[JournalEntry]) -> dict[UUID, tuple[str, UUID]]:
        """Return each journal's party, ("C" or "V", id), read off its document."""
        wanted: dict[str, list[JournalEntry]] = {}
        for entry in entries:
            if entry.source_module in _PARTIES and entry.source_id is not None:
                wanted.setdefault(entry.source_module, []).append(entry)
        answer: dict[UUID, tuple[str, UUID]] = {}
        for module, rows in wanted.items():
            path, name = _PARTIES[module].split(":")
            model = getattr(importlib.import_module(path), name)
            found = {
                document.id: document
                for document in self._session.scalars(
                    select(model).where(model.id.in_([r.source_id for r in rows]))
                ).all()
            }
            for entry in rows:
                document = found.get(entry.source_id)
                if document is None:
                    continue
                customer = getattr(document, "customer_id", None)
                vendor = getattr(document, "vendor_id", None)
                if customer is not None:
                    answer[entry.id] = ("C", customer)
                elif vendor is not None:
                    answer[entry.id] = ("V", vendor)
        return answer

    def _party_ledgers(
        self, parties: set[tuple[str, UUID]]
    ) -> dict[tuple[str, UUID], _Ledger]:
        """Name each party's ledger; a name two parties share gains the code."""
        from app.customers.models import Customer
        from app.vendors.models import Vendor

        rows: list[tuple[tuple[str, UUID], str, str, str | None]] = []
        customer_ids = [party_id for kind, party_id in parties if kind == "C"]
        vendor_ids = [party_id for kind, party_id in parties if kind == "V"]
        if customer_ids:
            for customer_id, name, code, gstin in self._session.execute(
                select(
                    Customer.id, Customer.name, Customer.code, Customer.gst_number
                ).where(Customer.id.in_(customer_ids))
            ).all():
                rows.append((("C", customer_id), name, code, gstin))
        if vendor_ids:
            for vendor_id, name, code, gstin in self._session.execute(
                select(Vendor.id, Vendor.name, Vendor.code, Vendor.gstin).where(
                    Vendor.id.in_(vendor_ids)
                )
            ).all():
                rows.append((("V", vendor_id), name, code, gstin))
        counts: dict[str, int] = {}
        for _, name, _, _ in rows:
            counts[name.lower()] = counts.get(name.lower(), 0) + 1
        return {
            key: _Ledger(
                name=name if counts[name.lower()] == 1 else f"{name} ({code})",
                parent="Sundry Debtors" if key[0] == "C" else "Sundry Creditors",
                gstin=(gstin or "").strip().upper() or None,
            )
            for key, name, code, gstin in rows
        }

    @staticmethod
    def _master(ledger: _Ledger) -> str:
        """Write one ledger master."""
        gst = (
            "<GSTREGISTRATIONTYPE>Regular</GSTREGISTRATIONTYPE>"
            f"<PARTYGSTIN>{escape(ledger.gstin)}</PARTYGSTIN>"
            if ledger.gstin
            else ""
        )
        return (
            '<TALLYMESSAGE xmlns:UDF="TallyUDF">'
            f'<LEDGER NAME={quoteattr(ledger.name)} ACTION="Create">'
            f"<NAME.LIST><NAME>{escape(ledger.name)}</NAME></NAME.LIST>"
            f"<PARENT>{escape(ledger.parent)}</PARENT>"
            f"{gst}"
            "</LEDGER></TALLYMESSAGE>"
        )

    @staticmethod
    def _voucher(
        entry: JournalEntry,
        rows: list[tuple[_Ledger, Decimal]],
        party: _Ledger | None,
    ) -> str:
        """Write one voucher; a debit is negative and deemed positive."""
        kind = VOUCHER_TYPES.get(entry.source_module or "", "")
        if not kind:
            if entry.source_module == "settlements":
                debited = [ledger for ledger, amount in rows if amount < ZERO]
                cash_like = {"Cash-in-Hand", "Bank Accounts"}
                kind = (
                    "Receipt"
                    if any(ledger.parent in cash_like for ledger in debited)
                    else "Payment"
                )
            else:
                kind = "Journal"
        narration = entry.description or entry.remarks or ""
        entries_xml = "".join(
            "<ALLLEDGERENTRIES.LIST>"
            f"<LEDGERNAME>{escape(ledger.name)}</LEDGERNAME>"
            f"<ISDEEMEDPOSITIVE>{'Yes' if amount < ZERO else 'No'}</ISDEEMEDPOSITIVE>"
            f"<AMOUNT>{amount:.2f}</AMOUNT>"
            "</ALLLEDGERENTRIES.LIST>"
            for ledger, amount in rows
        )
        party_xml = (
            f"<PARTYLEDGERNAME>{escape(party.name)}</PARTYLEDGERNAME>" if party else ""
        )
        return (
            '<TALLYMESSAGE xmlns:UDF="TallyUDF">'
            f'<VOUCHER VCHTYPE={quoteattr(kind)} ACTION="Create">'
            f"<DATE>{entry.journal_date:%Y%m%d}</DATE>"
            f"<VOUCHERTYPENAME>{escape(kind)}</VOUCHERTYPENAME>"
            f"<VOUCHERNUMBER>{escape(entry.reference_number)}</VOUCHERNUMBER>"
            f"{party_xml}"
            f"<NARRATION>{escape(narration)}</NARRATION>"
            f"{entries_xml}"
            "</VOUCHER></TALLYMESSAGE>"
        )


def _envelope(company: str, masters: list[str], vouchers: list[str]) -> bytes:
    """Wrap masters and vouchers in Tally's import envelope."""

    def block(report: str, messages: list[str]) -> str:
        return (
            "<IMPORTDATA><REQUESTDESC>"
            f"<REPORTNAME>{report}</REPORTNAME>"
            "<STATICVARIABLES>"
            f"<SVCURRENTCOMPANY>{escape(company)}</SVCURRENTCOMPANY>"
            "</STATICVARIABLES></REQUESTDESC><REQUESTDATA>"
            + "".join(messages)
            + "</REQUESTDATA></IMPORTDATA>"
        )

    body = block("All Masters", masters) + block("Vouchers", vouchers)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<ENVELOPE><HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER>"
        f"<BODY>{body}</BODY></ENVELOPE>"
    ).encode()
