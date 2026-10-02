"""A customer's bank accounts and the files kept on file for them (MST-4).

A distributor keeps a customer's KYC -- the GST certificate, a drug licence, a
signed credit agreement, a cancelled cheque -- and pays refunds and scheme
credits into the customer's bank account. Both were possible for a supplier
(``vendor_bank_accounts``, ``vendor_attachments``) and not for a customer.

Like every other attachment here, a file row records where the file is, not
the file. An account number is a payment instruction: who may change it is a
separate duty (``CUSTOMER_MANAGE_BANK_DETAILS``), and everybody else reads it
masked to its last four digits.
"""

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class CustomerBankAccount(BaseEntity):
    """One bank account a customer is paid into."""

    __tablename__ = "customer_bank_accounts"

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    customer_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    bank_name: Mapped[str] = mapped_column(String(150), nullable=False)
    account_name: Mapped[str] = mapped_column(String(150), nullable=False)
    account_number: Mapped[str] = mapped_column(String(64), nullable=False)
    ifsc: Mapped[str | None] = mapped_column(String(16))
    branch: Mapped[str | None] = mapped_column(String(120))
    upi_id: Mapped[str | None] = mapped_column(String(120))
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


class CustomerAttachment(BaseEntity):
    """One file kept on file for a customer -- KYC, an agreement, a licence."""

    __tablename__ = "customer_attachments"

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    customer_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    file_name: Mapped[str] = mapped_column(String(260), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(120))
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    #: What the file is, in a few words ("GST certificate").
    caption: Mapped[str | None] = mapped_column(String(200))
