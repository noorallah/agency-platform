"""A customer's bank accounts and files on record (MST-4, decision A68).

The accounts are replaced as a whole list, as a supplier's are, and only by
whoever holds ``CUSTOMER_MANAGE_BANK_DETAILS``: changing where a refund goes is
the redirection fraud the supplier side already guards. Everybody else reads
each number masked to its last four digits, and the audit trail records the
masked number too, since the trail is read far more widely than the account.

Files are added and removed one at a time; removing hides the row and the
trail keeps that it was there.
"""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.customers.models import Customer
from app.customers.models.customer_records import (
    CustomerAttachment,
    CustomerBankAccount,
)
from app.customers.schemas.records import (
    CustomerAttachmentWrite,
    CustomerBankAccountInput,
    CustomerBankAccountResponse,
)


def mask_account_number(number: str) -> str:
    """Return a number showing only its last four characters."""
    return "X" * max(len(number) - 4, 0) + number[-4:]


class CustomerRecordsService:
    """Keep a customer's bank accounts and files."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request's firm store."""
        self._session = session

    # ---- bank accounts ----------------------------------------------------

    def bank_accounts(
        self, customer_id: UUID, *, firm_id: UUID, unmasked: bool
    ) -> list[CustomerBankAccountResponse]:
        """Return the customer's live accounts, primary first."""
        self._customer(customer_id, firm_id=firm_id)
        rows = self._session.scalars(
            select(CustomerBankAccount)
            .where(
                CustomerBankAccount.customer_id == customer_id,
                CustomerBankAccount.firm_id == firm_id,
                CustomerBankAccount.is_deleted.is_(False),
            )
            .order_by(
                CustomerBankAccount.is_primary.desc(),
                CustomerBankAccount.created_at.asc(),
            )
        ).all()
        return [self._response(row, unmasked=unmasked) for row in rows]

    def replace_bank_accounts(
        self,
        customer_id: UUID,
        accounts: Sequence[CustomerBankAccountInput],
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> list[CustomerBankAccountResponse]:
        """Replace the customer's accounts with ``accounts`` and audit it."""
        self._customer(customer_id, firm_id=firm_id)
        if sum(account.is_primary for account in accounts) > 1:
            raise ValidationError("Only one bank account can be the primary one.")
        numbers = [account.account_number for account in accounts]
        if len(set(numbers)) != len(numbers):
            raise ValidationError("The same account number is listed twice.")
        current = self._session.scalars(
            select(CustomerBankAccount).where(
                CustomerBankAccount.customer_id == customer_id,
                CustomerBankAccount.firm_id == firm_id,
                CustomerBankAccount.is_deleted.is_(False),
            )
        ).all()
        before = [mask_account_number(row.account_number) for row in current]
        now = utc_now()
        for row in current:
            row.is_deleted = True
            row.deleted_at = now
            row.deleted_by = actor_id
        only = len(accounts) == 1
        for account in accounts:
            self._session.add(
                CustomerBankAccount(
                    firm_id=firm_id,
                    customer_id=customer_id,
                    **account.model_dump(exclude={"is_primary"}),
                    is_primary=account.is_primary or only,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        self._session.flush()
        record_audit(
            self._session,
            action="customer.bank_accounts.replaced",
            entity_type="customer",
            entity_id=customer_id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={"accounts": before},
            after_data={"accounts": [mask_account_number(n) for n in numbers]},
        )
        self._session.commit()
        return self.bank_accounts(customer_id, firm_id=firm_id, unmasked=True)

    # ---- files ------------------------------------------------------------

    def attachments(
        self, customer_id: UUID, *, firm_id: UUID
    ) -> list[CustomerAttachment]:
        """Return the customer's files, oldest first."""
        self._customer(customer_id, firm_id=firm_id)
        return list(
            self._session.scalars(
                select(CustomerAttachment)
                .where(
                    CustomerAttachment.customer_id == customer_id,
                    CustomerAttachment.firm_id == firm_id,
                    CustomerAttachment.is_deleted.is_(False),
                )
                .order_by(CustomerAttachment.created_at.asc())
            )
        )

    def attach(
        self,
        customer_id: UUID,
        files: Sequence[CustomerAttachmentWrite],
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> list[CustomerAttachment]:
        """Keep files on record for the customer and audit each."""
        self._customer(customer_id, firm_id=firm_id)
        if not files:
            raise ValidationError("Choose at least one file.")
        rows = [
            CustomerAttachment(
                firm_id=firm_id,
                customer_id=customer_id,
                **item.model_dump(),
                created_by=actor_id,
                updated_by=actor_id,
            )
            for item in files
        ]
        self._session.add_all(rows)
        self._session.flush()
        for row in rows:
            record_audit(
                self._session,
                action="customer.attachment.added",
                entity_type="customer",
                entity_id=customer_id,
                actor_id=actor_id,
                firm_id=firm_id,
                after_data={"file_name": row.file_name, "caption": row.caption},
            )
        self._session.commit()
        return rows

    def remove_attachment(
        self, customer_id: UUID, attachment_id: UUID, *, firm_id: UUID, actor_id: UUID
    ) -> None:
        """Hide one file; the trail keeps that it was there."""
        row = self._session.scalar(
            select(CustomerAttachment).where(
                CustomerAttachment.id == attachment_id,
                CustomerAttachment.customer_id == customer_id,
                CustomerAttachment.firm_id == firm_id,
                CustomerAttachment.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("File not found.")
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        record_audit(
            self._session,
            action="customer.attachment.removed",
            entity_type="customer",
            entity_id=customer_id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={"file_name": row.file_name, "caption": row.caption},
        )
        self._session.commit()

    # ---- helpers ----------------------------------------------------------

    def _customer(self, customer_id: UUID, *, firm_id: UUID) -> Customer:
        """Return the firm's live customer or raise."""
        row = self._session.scalar(
            select(Customer).where(
                Customer.id == customer_id,
                Customer.firm_id == firm_id,
                Customer.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Customer not found.")
        return row

    @staticmethod
    def _response(
        row: CustomerBankAccount, *, unmasked: bool
    ) -> CustomerBankAccountResponse:
        """Build one account's response, masking the number where asked."""
        response = CustomerBankAccountResponse.model_validate(row)
        if unmasked:
            return response
        return response.model_copy(
            update={
                "account_number": mask_account_number(row.account_number),
                "masked": True,
            }
        )
