"""Enquiries and leads before the quotation (SEL-10, decision A133).

A buyer asks before they buy. The enquiry records who asked -- a customer,
or a prospect not yet one -- what for, roughly what it is worth, who follows
it up and when next. It moves:

* **Open** -- asked, being followed up; each contact is logged with the next
  date, and the *follow-ups due* list is what a salesman works through.
* **Quoted** -- *Convert to quotation* raises the quotation from its lines,
  and a prospect becomes a customer then and only then, in the same
  transaction.
* **Won** -- the quotation became an order.
* **Lost** -- closed with a reason from a fixed list (price, competitor, no
  stock, no response, not needed, other), which is what the lost report
  counts.

The way ERPNext's Lead -> Opportunity -> Quotation and Zoho's CRM-lite work.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, select

from app.common.audit.services import record_audit
from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO
from app.core.validation import validate_email, validate_phone
from app.document_framework.services.transactional_document_service import (
    DocumentStateSpec,
    DocumentTypeSpec,
    TransactionalDocumentService,
)
from app.enquiry.models import Enquiry, EnquiryFollowUp, EnquiryLine
from app.products.models import Product

SOURCES = ("WALK_IN", "PHONE", "WHATSAPP", "REFERRAL", "EXHIBITION", "WEBSITE", "OTHER")
LOST_REASONS = (
    "PRICE",
    "COMPETITOR",
    "NO_STOCK",
    "NO_RESPONSE",
    "NOT_NEEDED",
    "OTHER",
)
_LIVE = ("OPEN", "QUOTED")


class EnquiryLineWrite(BaseModel):
    """One thing asked for."""

    model_config = ConfigDict(extra="forbid")

    product_id: UUID | None = None
    description: str | None = Field(default=None, max_length=500)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    expected_price: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=4
    )

    @model_validator(mode="after")
    def _says_what(self) -> EnquiryLineWrite:
        """Require a product or words saying what was asked for."""
        if self.product_id is None and not (self.description or "").strip():
            raise ValueError("A line names a product or describes what was asked.")
        return self


class EnquiryWrite(BaseModel):
    """An enquiry: who asked, what for, and when to follow up."""

    model_config = ConfigDict(extra="forbid")

    enquiry_date: date
    branch_id: UUID
    customer_id: UUID | None = None
    prospect_name: str | None = Field(default=None, max_length=200)
    prospect_company: str | None = Field(default=None, max_length=200)
    prospect_phone: str | None = Field(default=None, max_length=20)
    prospect_email: str | None = Field(default=None, max_length=320)
    prospect_city: str | None = Field(default=None, max_length=100)
    source: str = Field(
        default="OTHER",
        pattern="^(WALK_IN|PHONE|WHATSAPP|REFERRAL|EXHIBITION|WEBSITE|OTHER)$",
    )
    salesman_id: UUID | None = None
    expected_value: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=2
    )
    expected_close_on: date | None = None
    next_follow_up_on: date | None = None
    remarks: str | None = Field(default=None, max_length=2000)
    lines: list[EnquiryLineWrite] = Field(default_factory=list, max_length=200)

    @field_validator("prospect_phone")
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        """Check the phone as the customer master will on conversion."""
        return validate_phone(value) if value and value.strip() else None

    @field_validator("prospect_email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        """Check the email as the customer master will on conversion."""
        return validate_email(value) if value and value.strip() else None

    @model_validator(mode="after")
    def _a_buyer(self) -> EnquiryWrite:
        """Require a customer, or a prospect with a name."""
        if self.customer_id is None and not (self.prospect_name or "").strip():
            raise ValueError("Name the customer or the prospect who asked.")
        return self


class EnquiryFollowUpWrite(BaseModel):
    """One contact with the buyer."""

    model_config = ConfigDict(extra="forbid")

    followed_on: date
    note: str = Field(min_length=1, max_length=2000)
    next_follow_up_on: date | None = None


class EnquiryLostWrite(BaseModel):
    """Why the enquiry did not become a sale."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(
        pattern="^(PRICE|COMPETITOR|NO_STOCK|NO_RESPONSE|NOT_NEEDED|OTHER)$"
    )
    remarks: str | None = Field(default=None, max_length=1000)


class EnquiryConvertWrite(BaseModel):
    """What a quotation needs that an enquiry does not hold."""

    model_config = ConfigDict(extra="forbid")

    warehouse_id: UUID
    quotation_date: date
    valid_until: date
    #: A prospect becomes a customer of this kind; blank code takes the
    #: firm's series.
    customer_type: str = Field(default="BUSINESS", pattern="^(BUSINESS|INDIVIDUAL)$")
    customer_code: str | None = Field(default=None, max_length=50)


class EnquiryLineResponse(BaseModel):
    """One line as recorded."""

    model_config = ConfigDict(extra="forbid")

    line_number: int
    product_id: UUID | None
    product_name: str | None
    description: str | None
    quantity: Decimal
    expected_price: Decimal | None


class EnquiryFollowUpResponse(BaseModel):
    """One logged contact."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    followed_on: date
    note: str
    next_follow_up_on: date | None
    created_by: UUID | None


class EnquiryResponse(BaseModel):
    """One enquiry with its lines and follow-ups."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    enquiry_number: str
    enquiry_date: date
    branch_id: UUID
    customer_id: UUID | None
    customer_name: str | None
    prospect_name: str | None
    prospect_company: str | None
    prospect_phone: str | None
    prospect_email: str | None
    prospect_city: str | None
    source: str
    salesman_id: UUID | None
    expected_value: Decimal
    expected_close_on: date | None
    next_follow_up_on: date | None
    status: str
    lost_reason: str | None
    lost_remarks: str | None
    quotation_id: UUID | None
    remarks: str | None
    version: int
    lines: list[EnquiryLineResponse]
    follow_ups: list[EnquiryFollowUpResponse]


class LostReasonRow(BaseModel):
    """How many enquiries were lost for one reason, and what they were worth."""

    model_config = ConfigDict(extra="forbid")

    reason: str
    count: int
    expected_value: Decimal


class EnquiryService(TransactionalDocumentService):
    """Record, follow up, convert and close enquiries."""

    DOCUMENT = DocumentTypeSpec(
        code="ENQUIRY",
        name="Enquiry",
        description="A buyer's enquiry before a quotation.",
        category="SALES",
        module="enquiry",
        prefix="ENQ",
        rule_code="ENQUIRY_DEFAULT",
        rule_name="Enquiry Default Numbering",
        states=(
            DocumentStateSpec("OPEN", "Open", 10),
            DocumentStateSpec("QUOTED", "Quoted", 20),
            DocumentStateSpec("WON", "Won", 30, is_terminal=True),
            DocumentStateSpec("LOST", "Lost", 90, is_terminal=True),
        ),
    )

    # ---- writing -------------------------------------------------------

    def create(self, data: EnquiryWrite, *, firm_id: UUID, actor_id: UUID) -> Enquiry:
        """Record an enquiry and number it; commit."""
        self._check(data, firm_id)
        _, rule = self._ensure_document_setup(firm_id=firm_id, actor_id=actor_id)
        number = self._issue_number(
            rule,
            typed=None,
            number_column=Enquiry.enquiry_number,
            firm_id=firm_id,
            document_date=data.enquiry_date,
            actor_id=actor_id,
            branch_code=self._scope_code(data.branch_id),
            company_code=self._company_code(firm_id),
        )
        row = Enquiry(
            firm_id=firm_id,
            enquiry_number=number,
            status="OPEN",
            created_by=actor_id,
            updated_by=actor_id,
            **self._fields(data),
        )
        self._session.add(row)
        self._flush_or_conflict("Enquiry number already exists in this firm.")
        self._write_lines(row, data.lines, actor_id)
        self._audit("enquiry.created", row, actor_id)
        self._session.commit()
        return row

    def update(
        self,
        enquiry_id: UUID,
        data: EnquiryWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
        expected_version: int | None = None,
    ) -> Enquiry:
        """Rewrite an open enquiry; commit.

        An enquiry's lines have nothing downstream until it is quoted, and
        a quoted one cannot be changed, so lines are replaced.
        """
        from app.core.concurrency import assert_version

        row = self.get(enquiry_id, firm_id=firm_id)
        assert_version(row.version, expected_version)
        if row.status != "OPEN":
            raise ValidationError("Only an open enquiry can be changed.")
        self._check(data, firm_id)
        for name, value in self._fields(data).items():
            setattr(row, name, value)
        row.updated_by = actor_id
        for line in self._lines([row.id]):
            self._session.delete(line)
        self._session.flush()
        self._write_lines(row, data.lines, actor_id)
        self._audit("enquiry.updated", row, actor_id)
        self._session.commit()
        return row

    def follow_up(
        self,
        enquiry_id: UUID,
        data: EnquiryFollowUpWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> Enquiry:
        """Log a contact and move the next follow-up date; commit."""
        row = self.get(enquiry_id, firm_id=firm_id)
        if row.status not in _LIVE:
            raise ValidationError("A closed enquiry is not followed up.")
        if data.next_follow_up_on is not None and (
            data.next_follow_up_on < data.followed_on
        ):
            raise ValidationError("The next follow-up comes after this one.")
        self._session.add(
            EnquiryFollowUp(
                enquiry_id=row.id,
                firm_id=firm_id,
                followed_on=data.followed_on,
                note=data.note.strip(),
                next_follow_up_on=data.next_follow_up_on,
                created_by=actor_id,
                updated_by=actor_id,
            )
        )
        row.next_follow_up_on = data.next_follow_up_on
        row.updated_by = actor_id
        self._audit("enquiry.followed_up", row, actor_id)
        self._session.commit()
        return row

    def mark_lost(
        self,
        enquiry_id: UUID,
        data: EnquiryLostWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> Enquiry:
        """Close an enquiry as lost, with the reason; commit."""
        row = self.get(enquiry_id, firm_id=firm_id)
        if row.status not in _LIVE:
            raise ValidationError("This enquiry is already closed.")
        row.status = "LOST"
        row.lost_reason = data.reason
        row.lost_remarks = (data.remarks or "").strip() or None
        row.next_follow_up_on = None
        row.updated_by = actor_id
        self._audit("enquiry.lost", row, actor_id)
        self._session.commit()
        return row

    def convert(
        self,
        enquiry_id: UUID,
        data: EnquiryConvertWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> Enquiry:
        """Raise the quotation, making a prospect a customer; commit once.

        Raises:
            ValidationError: If it is not open, has no lines, or a line names
                no product yet.

        """
        from app.customers.schemas import CustomerCreate
        from app.customers.services import CustomerService
        from app.quotation.schemas import QuotationCreate
        from app.quotation.services import QuotationService

        row = self.get(enquiry_id, firm_id=firm_id)
        if row.status != "OPEN":
            raise ValidationError("Only an open enquiry is converted.")
        lines = self._lines([row.id])
        if not lines:
            raise ValidationError("Add what was asked for before quoting it.")
        unmatched = [line.line_number for line in lines if line.product_id is None]
        if unmatched:
            raise ValidationError(
                "Match line "
                + ", ".join(str(n) for n in unmatched)
                + " to a product before quoting."
            )
        if data.valid_until < data.quotation_date:
            raise ValidationError("A quotation is valid until after its date.")
        customer_id = row.customer_id
        if customer_id is None:
            customer = CustomerService(self._session).stage_create(
                CustomerCreate.model_validate(
                    {
                        "code": data.customer_code,
                        "customer_type": data.customer_type,
                        "name": row.prospect_company or row.prospect_name,
                        "phone": row.prospect_phone,
                        "email": row.prospect_email,
                        "currency_code": (
                            FirmMetadataReader(self._session).get(firm_id).currency_code
                            or "INR"
                        ),
                    }
                ),
                firm_id=firm_id,
                actor_id=actor_id,
            )
            customer_id = customer.id
            row.customer_id = customer.id
        quotation = QuotationService(self._session).stage_quotation(
            QuotationCreate.model_validate(
                {
                    "customer_id": customer_id,
                    "salesman_id": row.salesman_id,
                    "branch_id": row.branch_id,
                    "warehouse_id": data.warehouse_id,
                    "quotation_date": data.quotation_date,
                    "valid_until": data.valid_until,
                    "customer_reference": row.enquiry_number,
                    "remarks": row.remarks,
                    "lines": [
                        {
                            "line_number": line.line_number,
                            "product_id": line.product_id,
                            "description": line.description,
                            "quantity": line.quantity,
                            **(
                                {"unit_price": line.expected_price}
                                if line.expected_price is not None
                                else {}
                            ),
                        }
                        for line in lines
                    ],
                }
            ),
            firm_id=firm_id,
            actor_id=actor_id,
        )
        row.quotation_id = quotation.id
        row.status = "QUOTED"
        row.updated_by = actor_id
        self._audit("enquiry.quoted", row, actor_id)
        self._session.commit()
        return row

    def won_from_quotation(
        self, quotation_id: UUID, *, firm_id: UUID, actor_id: UUID
    ) -> None:
        """Mark the enquiry behind a quotation won; stages, never commits."""
        row = self._session.scalar(
            select(Enquiry).where(
                Enquiry.firm_id == firm_id,
                Enquiry.quotation_id == quotation_id,
                Enquiry.is_deleted.is_(False),
            )
        )
        if row is None or row.status != "QUOTED":
            return
        row.status = "WON"
        row.next_follow_up_on = None
        row.updated_by = actor_id
        self._audit("enquiry.won", row, actor_id)

    # ---- reads ---------------------------------------------------------

    def get(self, enquiry_id: UUID, *, firm_id: UUID) -> Enquiry:
        """Return one of the firm's enquiries."""
        row = self._session.get(Enquiry, enquiry_id)
        if row is None or row.is_deleted or row.firm_id != firm_id:
            raise ResourceNotFoundError("Enquiry not found.")
        return row

    def list_rows(
        self,
        firm_id: UUID,
        *,
        status: str | None = None,
        salesman_id: UUID | None = None,
        due_on: date | None = None,
    ) -> list[Enquiry]:
        """Return the firm's enquiries, newest first.

        ``due_on`` lists the live ones whose next follow-up falls on or
        before that day, soonest first -- the follow-ups due.
        """
        query = select(Enquiry).where(
            Enquiry.firm_id == firm_id, Enquiry.is_deleted.is_(False)
        )
        if status:
            query = query.where(Enquiry.status == status.upper())
        if salesman_id is not None:
            query = query.where(Enquiry.salesman_id == salesman_id)
        if due_on is not None:
            query = query.where(
                Enquiry.status.in_(_LIVE),
                Enquiry.next_follow_up_on.is_not(None),
                Enquiry.next_follow_up_on <= due_on,
            ).order_by(Enquiry.next_follow_up_on, Enquiry.enquiry_number)
        else:
            query = query.order_by(
                Enquiry.enquiry_date.desc(),
                Enquiry.enquiry_number.desc(),
                Enquiry.id.desc(),
            )
        return list(self._session.scalars(query.limit(1000)).all())

    def list_page(
        self,
        firm_id: UUID,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
        salesman_id: UUID | None = None,
    ) -> tuple[list[Enquiry], int]:
        """Return one page of the firm's enquiries, newest first, and the count."""
        conditions = [Enquiry.firm_id == firm_id, Enquiry.is_deleted.is_(False)]
        if status:
            conditions.append(Enquiry.status == status.upper())
        if salesman_id is not None:
            conditions.append(Enquiry.salesman_id == salesman_id)
        total = int(
            self._session.scalar(
                select(func.count()).select_from(Enquiry).where(*conditions)
            )
            or 0
        )
        rows = self._session.scalars(
            select(Enquiry)
            .where(*conditions)
            .order_by(
                Enquiry.enquiry_date.desc(),
                Enquiry.enquiry_number.desc(),
                Enquiry.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(rows), total

    def lost_reasons(
        self, firm_id: UUID, *, from_date: date, to_date: date
    ) -> list[LostReasonRow]:
        """Count lost enquiries by reason in a period, with what they were worth."""
        rows = self._session.execute(
            select(
                Enquiry.lost_reason,
                func.count(Enquiry.id),
                func.coalesce(func.sum(Enquiry.expected_value), 0),
            )
            .where(
                Enquiry.firm_id == firm_id,
                Enquiry.is_deleted.is_(False),
                Enquiry.status == "LOST",
                Enquiry.enquiry_date >= from_date,
                Enquiry.enquiry_date <= to_date,
            )
            .group_by(Enquiry.lost_reason)
        ).all()
        return sorted(
            (
                LostReasonRow(
                    reason=str(reason or "OTHER"),
                    count=int(count),
                    expected_value=Decimal(str(value or 0)),
                )
                for reason, count, value in rows
            ),
            key=lambda row: (-row.count, row.reason),
        )

    def responses(self, rows: list[Enquiry]) -> list[EnquiryResponse]:
        """Shape enquiries with their lines and follow-ups, one read per table."""
        if not rows:
            return []
        from app.customers.models import Customer

        ids = [row.id for row in rows]
        lines = self._lines(ids)
        follow_ups = list(
            self._session.scalars(
                select(EnquiryFollowUp)
                .where(
                    EnquiryFollowUp.enquiry_id.in_(ids),
                    EnquiryFollowUp.is_deleted.is_(False),
                )
                .order_by(EnquiryFollowUp.followed_on, EnquiryFollowUp.created_at)
            ).all()
        )
        product_ids = {line.product_id for line in lines if line.product_id}
        products: dict[UUID, str] = (
            {
                product_id: name
                for product_id, name in self._session.execute(
                    select(Product.id, Product.name).where(Product.id.in_(product_ids))
                ).all()
            }
            if product_ids
            else {}
        )
        customer_ids = {row.customer_id for row in rows if row.customer_id}
        customers: dict[UUID, str] = (
            {
                customer_id: name
                for customer_id, name in self._session.execute(
                    select(Customer.id, Customer.name).where(
                        Customer.id.in_(customer_ids)
                    )
                ).all()
            }
            if customer_ids
            else {}
        )
        return [
            EnquiryResponse(
                id=row.id,
                enquiry_number=row.enquiry_number,
                enquiry_date=row.enquiry_date,
                branch_id=row.branch_id,
                customer_id=row.customer_id,
                customer_name=(
                    customers.get(row.customer_id) if row.customer_id else None
                ),
                prospect_name=row.prospect_name,
                prospect_company=row.prospect_company,
                prospect_phone=row.prospect_phone,
                prospect_email=row.prospect_email,
                prospect_city=row.prospect_city,
                source=row.source,
                salesman_id=row.salesman_id,
                expected_value=row.expected_value,
                expected_close_on=row.expected_close_on,
                next_follow_up_on=row.next_follow_up_on,
                status=row.status,
                lost_reason=row.lost_reason,
                lost_remarks=row.lost_remarks,
                quotation_id=row.quotation_id,
                remarks=row.remarks,
                version=row.version,
                lines=[
                    EnquiryLineResponse(
                        line_number=line.line_number,
                        product_id=line.product_id,
                        product_name=(
                            products.get(line.product_id) if line.product_id else None
                        ),
                        description=line.description,
                        quantity=line.quantity,
                        expected_price=line.expected_price,
                    )
                    for line in lines
                    if line.enquiry_id == row.id
                ],
                follow_ups=[
                    EnquiryFollowUpResponse(
                        id=item.id,
                        followed_on=item.followed_on,
                        note=item.note,
                        next_follow_up_on=item.next_follow_up_on,
                        created_by=item.created_by,
                    )
                    for item in follow_ups
                    if item.enquiry_id == row.id
                ],
            )
            for row in rows
        ]

    # ---- helpers -------------------------------------------------------

    def _check(self, data: EnquiryWrite, firm_id: UUID) -> None:
        """Refuse a customer, branch or product that is not the firm's."""
        from app.branches.models import Branch
        from app.customers.models import Customer

        branch = self._session.get(Branch, data.branch_id)
        if branch is None or branch.is_deleted or branch.firm_id != firm_id:
            raise ValidationError("That branch is not one of this firm's.")
        if data.customer_id is not None:
            customer = self._session.get(Customer, data.customer_id)
            if customer is None or customer.is_deleted or customer.firm_id != firm_id:
                raise ValidationError("That customer is not one of this firm's.")
        ids = {line.product_id for line in data.lines if line.product_id}
        if ids:
            known = set(
                self._session.scalars(
                    select(Product.id).where(
                        Product.id.in_(ids),
                        Product.firm_id == firm_id,
                        Product.is_deleted.is_(False),
                    )
                ).all()
            )
            if ids - known:
                raise ValidationError("A line names a product that is not the firm's.")
        if data.next_follow_up_on is not None and (
            data.next_follow_up_on < data.enquiry_date
        ):
            raise ValidationError("A follow-up comes on or after the enquiry.")

    @staticmethod
    def _fields(data: EnquiryWrite) -> dict[str, object]:
        """Return the header columns a write sets."""
        return {
            "enquiry_date": data.enquiry_date,
            "branch_id": data.branch_id,
            "customer_id": data.customer_id,
            "prospect_name": (data.prospect_name or "").strip() or None,
            "prospect_company": (data.prospect_company or "").strip() or None,
            "prospect_phone": (data.prospect_phone or "").strip() or None,
            "prospect_email": (data.prospect_email or "").strip() or None,
            "prospect_city": (data.prospect_city or "").strip() or None,
            "source": data.source,
            "salesman_id": data.salesman_id,
            "expected_value": data.expected_value,
            "expected_close_on": data.expected_close_on,
            "next_follow_up_on": data.next_follow_up_on,
            "remarks": data.remarks,
        }

    def _write_lines(
        self, row: Enquiry, lines: list[EnquiryLineWrite], actor_id: UUID
    ) -> None:
        """Stage the enquiry's lines, numbered in order."""
        for number, line in enumerate(lines, start=1):
            self._session.add(
                EnquiryLine(
                    enquiry_id=row.id,
                    firm_id=row.firm_id,
                    line_number=number,
                    product_id=line.product_id,
                    description=(line.description or "").strip() or None,
                    quantity=line.quantity,
                    expected_price=line.expected_price,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )

    def _lines(self, enquiry_ids: list[UUID]) -> list[EnquiryLine]:
        """Return the enquiries' lines in order."""
        return list(
            self._session.scalars(
                select(EnquiryLine)
                .where(
                    EnquiryLine.enquiry_id.in_(enquiry_ids),
                    EnquiryLine.is_deleted.is_(False),
                )
                .order_by(EnquiryLine.enquiry_id, EnquiryLine.line_number)
            ).all()
        )

    def _audit(self, action: str, row: Enquiry, actor_id: UUID) -> None:
        """Write one audit row for an enquiry."""
        record_audit(
            self._session,
            action=action,
            entity_type="enquiry",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            after_data={
                "enquiry_number": row.enquiry_number,
                "status": row.status,
                "expected_value": str(row.expected_value or ZERO),
                "at": utc_now().isoformat(),
            },
        )
