"""The firm's own bank account details and the block bills print (ACC-4, A81).

Details hang off a bank ledger account -- an asset account -- one row each,
saved whole and audited. At most one is marked to print on documents; marking
another moves the mark, since a bill names one account to pay into.

Who reads the full number: whoever may change the details (``ACCOUNT_MANAGE``)
or pays from the account (``PAYMENT_CREATE``). Everybody else holding
``ACCOUNT_VIEW`` reads the last four, and the audit trail records only the last
four, because the trail is read far more widely than the account. The printed
bill carries the whole number -- a customer cannot pay into four digits.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.strings import mask_account_number
from app.finance.models import AccountType, LedgerAccount
from app.finance.models.bank_details import BankAccountDetails
from app.finance.schemas.bank_details import (
    BankAccountDetailsResponse,
    BankAccountDetailsWrite,
)

#: The codes that see a firm bank account number whole.
UNMASKING_PERMISSIONS = ("ACCOUNT_MANAGE", "PAYMENT_CREATE")


@dataclass(frozen=True, slots=True)
class PrintedBankAccount:
    """What a bill prints about the account to pay into."""

    lines: list[str]
    upi_id: str | None


class BankDetailsService:
    """Keep the firm's bank account details."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request's firm store."""
        self._session = session

    def list_details(
        self, firm_id: UUID, *, unmasked: bool
    ) -> list[BankAccountDetailsResponse]:
        """Return every account's details, the printed one first."""
        rows = self._session.execute(
            select(BankAccountDetails, LedgerAccount)
            .join(
                LedgerAccount, LedgerAccount.id == BankAccountDetails.ledger_account_id
            )
            .where(
                BankAccountDetails.firm_id == firm_id,
                BankAccountDetails.is_deleted.is_(False),
            )
            .order_by(BankAccountDetails.print_on_documents.desc(), LedgerAccount.code)
        ).all()
        return [
            self._response(row, account, unmasked=unmasked) for row, account in rows
        ]

    def get(
        self, ledger_account_id: UUID, *, firm_id: UUID, unmasked: bool
    ) -> BankAccountDetailsResponse:
        """Return one account's details, or raise when none are kept."""
        account = self._account(ledger_account_id, firm_id=firm_id)
        row = self._row(ledger_account_id, firm_id=firm_id)
        if row is None:
            raise ResourceNotFoundError("No bank details are kept for this account.")
        return self._response(row, account, unmasked=unmasked)

    def save(
        self,
        ledger_account_id: UUID,
        payload: BankAccountDetailsWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> BankAccountDetailsResponse:
        """Store an account's details whole, moving the print mark if asked."""
        account = self._account(ledger_account_id, firm_id=firm_id)
        row = self._row(ledger_account_id, firm_id=firm_id)
        before = None if row is None else self._audit_view(row)
        if payload.print_on_documents:
            self._clear_print_mark(firm_id, keep=ledger_account_id, actor_id=actor_id)
        if row is None:
            row = BankAccountDetails(
                firm_id=firm_id,
                ledger_account_id=ledger_account_id,
                created_by=actor_id,
            )
            self._session.add(row)
        for field, value in payload.model_dump(mode="python").items():
            setattr(row, field, value)
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="bank_account_details.saved",
            entity_type="bank_account_details",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data=self._audit_view(row),
        )
        self._session.commit()
        return self._response(row, account, unmasked=True)

    def remove(self, ledger_account_id: UUID, *, firm_id: UUID, actor_id: UUID) -> None:
        """Drop an account's details; the ledger account itself stays."""
        self._account(ledger_account_id, firm_id=firm_id)
        row = self._row(ledger_account_id, firm_id=firm_id)
        if row is None:
            raise ResourceNotFoundError("No bank details are kept for this account.")
        before = self._audit_view(row)
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.print_on_documents = False
        self._session.flush()
        record_audit(
            self._session,
            action="bank_account_details.removed",
            entity_type="bank_account_details",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data=None,
        )
        self._session.commit()

    def printed(self, firm_id: UUID) -> PrintedBankAccount | None:
        """Return the block bills print, or None when no account is marked."""
        row = self._session.scalar(
            select(BankAccountDetails).where(
                BankAccountDetails.firm_id == firm_id,
                BankAccountDetails.print_on_documents.is_(True),
                BankAccountDetails.is_deleted.is_(False),
            )
        )
        if row is None:
            return None
        bank = row.bank_name if not row.branch else f"{row.bank_name}, {row.branch}"
        lines = [
            f"Bank: {bank}",
            f"A/c name: {row.account_name}",
            f"A/c no.: {row.account_number}",
        ]
        if row.ifsc:
            lines.append(f"IFSC: {row.ifsc}")
        if row.swift_code:
            lines.append(f"SWIFT: {row.swift_code}")
        return PrintedBankAccount(lines=lines, upi_id=row.upi_id)

    # ---- internals --------------------------------------------------------

    def _account(self, ledger_account_id: UUID, *, firm_id: UUID) -> LedgerAccount:
        """Return the firm's live asset account, or raise."""
        account = self._session.scalar(
            select(LedgerAccount).where(
                LedgerAccount.id == ledger_account_id,
                LedgerAccount.firm_id == firm_id,
                LedgerAccount.is_deleted.is_(False),
            )
        )
        if account is None:
            raise ResourceNotFoundError("Ledger account not found.")
        if account.account_type != AccountType.ASSET.value:
            raise ValidationError(
                f"{account.name} is not an asset account; bank details belong "
                "on the ledger account that holds the bank balance."
            )
        return account

    def _row(
        self, ledger_account_id: UUID, *, firm_id: UUID
    ) -> BankAccountDetails | None:
        """Return the account's live details row, if any."""
        return self._session.scalar(
            select(BankAccountDetails).where(
                BankAccountDetails.ledger_account_id == ledger_account_id,
                BankAccountDetails.firm_id == firm_id,
                BankAccountDetails.is_deleted.is_(False),
            )
        )

    def _clear_print_mark(self, firm_id: UUID, *, keep: UUID, actor_id: UUID) -> None:
        """Take the print mark off every other account, before setting it.

        Flushed first: the one-per-firm index is checked per statement, so the
        old mark has to be gone before the new one is written.
        """
        others = self._session.scalars(
            select(BankAccountDetails).where(
                BankAccountDetails.firm_id == firm_id,
                BankAccountDetails.print_on_documents.is_(True),
                BankAccountDetails.is_deleted.is_(False),
                BankAccountDetails.ledger_account_id != keep,
            )
        ).all()
        for other in others:
            other.print_on_documents = False
            other.updated_by = actor_id
        if others:
            self._session.flush()

    @staticmethod
    def _audit_view(row: BankAccountDetails) -> dict[str, object]:
        """Return what the trail keeps: everything, the number masked."""
        return {
            "ledger_account_id": str(row.ledger_account_id),
            "bank_name": row.bank_name,
            "account_name": row.account_name,
            "account_number": mask_account_number(row.account_number),
            "ifsc": row.ifsc,
            "branch": row.branch,
            "account_kind": row.account_kind,
            "print_on_documents": row.print_on_documents,
        }

    @staticmethod
    def _response(
        row: BankAccountDetails, account: LedgerAccount, *, unmasked: bool
    ) -> BankAccountDetailsResponse:
        """Build one response, masking the number unless the caller may see it."""
        return BankAccountDetailsResponse(
            id=row.id,
            ledger_account_id=row.ledger_account_id,
            ledger_account_code=account.code,
            ledger_account_name=account.name,
            bank_name=row.bank_name,
            account_name=row.account_name,
            account_number=(
                row.account_number
                if unmasked
                else mask_account_number(row.account_number)
            ),
            masked=not unmasked,
            ifsc=row.ifsc,
            branch=row.branch,
            account_kind=row.account_kind,
            swift_code=row.swift_code,
            upi_id=row.upi_id,
            print_on_documents=row.print_on_documents,
            version=row.version,
            updated_at=row.updated_at,
        )
