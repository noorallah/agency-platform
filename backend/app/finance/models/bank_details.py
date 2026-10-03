"""The firm's own bank account details, kept on its bank ledger (ACC-4, A81).

A bank ledger account says how much is in the bank; this says which account it
is -- bank, account name and number, IFSC and branch -- so a bill can tell the
customer where to pay. One row per bank ledger account, and at most one per
firm marked to print on documents, which Tally calls the bank printed on the
invoice and Zoho the account on the template.

The number is printed in full, since a customer cannot pay into four digits,
but the API shows it whole only to whoever may change it or pays from it.
"""

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class BankAccountDetails(BaseEntity):
    """One bank ledger account's bank, number and IFSC."""

    __tablename__ = "bank_account_details"
    __table_args__ = (
        Index(
            "UQ_bank_account_details_account_active",
            "firm_id",
            "ledger_account_id",
            unique=True,
            postgresql_where=text("is_deleted IS FALSE"),
            sqlite_where=text("is_deleted = 0"),
        ),
        Index(
            "UQ_bank_account_details_printed_active",
            "firm_id",
            unique=True,
            postgresql_where=text("is_deleted IS FALSE AND print_on_documents IS TRUE"),
            sqlite_where=text("is_deleted = 0 AND print_on_documents = 1"),
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    #: The bank ledger account these details describe.
    ledger_account_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("ledger_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    bank_name: Mapped[str] = mapped_column(String(150), nullable=False)
    #: The name the account is held in -- usually the firm's legal name.
    account_name: Mapped[str] = mapped_column(String(150), nullable=False)
    account_number: Mapped[str] = mapped_column(String(64), nullable=False)
    ifsc: Mapped[str | None] = mapped_column(String(16))
    branch: Mapped[str | None] = mapped_column(String(120))
    #: CURRENT, SAVINGS, CASH_CREDIT or OVERDRAFT.
    account_kind: Mapped[str | None] = mapped_column(String(20))
    swift_code: Mapped[str | None] = mapped_column(String(16))
    #: Printed as the bill's pay-by-UPI code when the template names none.
    upi_id: Mapped[str | None] = mapped_column(String(120))
    #: The account bills tell customers to pay into; one per firm.
    print_on_documents: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
