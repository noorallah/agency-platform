"""Enquiries, what was asked for, and each follow-up (SEL-10)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class Enquiry(BaseEntity):
    """A buyer's enquiry before any quotation (decision A133).

    The buyer is a customer already, or a prospect described here until a
    quotation is raised -- only then does the prospect become a customer.
    """

    __tablename__ = "enquiries"
    __table_args__ = (
        Index("IX_enquiries_firm_status", "firm_id", "status"),
        Index("IX_enquiries_firm_follow_up", "firm_id", "next_follow_up_on"),
        Index(
            "UQ_enquiries_number_active",
            "firm_id",
            "enquiry_number",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    enquiry_number: Mapped[str] = mapped_column(String(60), nullable=False)
    enquiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    branch_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    customer_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("customers.id", ondelete="RESTRICT")
    )
    prospect_name: Mapped[str | None] = mapped_column(String(200))
    prospect_company: Mapped[str | None] = mapped_column(String(200))
    prospect_phone: Mapped[str | None] = mapped_column(String(20))
    prospect_email: Mapped[str | None] = mapped_column(String(320))
    prospect_city: Mapped[str | None] = mapped_column(String(100))
    #: Walk-in, phone, WhatsApp, referral, exhibition, website or other.
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="OTHER")
    #: The salesman following it up; a user, read from the platform.
    salesman_id: Mapped[UUID | None] = mapped_column(UUIDType())
    expected_value: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=0, server_default="0"
    )
    expected_close_on: Mapped[date | None] = mapped_column(Date)
    next_follow_up_on: Mapped[date | None] = mapped_column(Date)
    #: ``OPEN``, ``QUOTED``, ``WON`` or ``LOST``.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    lost_reason: Mapped[str | None] = mapped_column(String(40))
    lost_remarks: Mapped[str | None] = mapped_column(Text)
    quotation_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("sales_quotations.id", ondelete="SET NULL")
    )
    remarks: Mapped[str | None] = mapped_column(Text)


class EnquiryLine(BaseEntity):
    """One thing asked for: a product, or words until it is matched to one."""

    __tablename__ = "enquiry_lines"
    __table_args__ = (Index("IX_enquiry_lines_enquiry", "enquiry_id"),)

    enquiry_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("enquiries.id", ondelete="CASCADE"), nullable=False
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="RESTRICT")
    )
    description: Mapped[str | None] = mapped_column(String(500))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    expected_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))


class EnquiryFollowUp(BaseEntity):
    """One contact with the buyer and what was agreed."""

    __tablename__ = "enquiry_follow_ups"
    __table_args__ = (Index("IX_enquiry_follow_ups_enquiry", "enquiry_id"),)

    enquiry_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("enquiries.id", ondelete="CASCADE"), nullable=False
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    followed_on: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    next_follow_up_on: Mapped[date | None] = mapped_column(Date)
