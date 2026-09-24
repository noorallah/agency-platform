"""Raise, issue and withdraw a proforma invoice.

The two rules that make this document what it is, and that everything below
serves:

**It posts nothing.** No journal, no receivable, no stock, no tax return. There
is no code here that could -- the model carries no journal or receivable column
to write to -- and that is deliberate rather than an omission.

**Its lines are snapshotted from the order, not sent by the caller.** A caller
that could name its own lines could state a price the order never agreed, and
the customer would be arranging payment against a figure nothing backs.
"""

from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, select

from app.common.audit.services import record_audit
from app.core.concurrency import assert_version
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.pagination import WHOLE_HISTORY, ReportWindow, mapped_like
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO, quantize_money
from app.customers.models import Customer
from app.document_framework.models import DocumentNumberingRule
from app.document_framework.services.transactional_document_service import (
    DocumentStateSpec,
    DocumentTypeSpec,
    TransactionalDocumentService,
)
from app.products.models import Product
from app.proforma.models import ProformaInvoice, ProformaInvoiceLine, ProformaStatus
from app.proforma.schemas import (
    ProformaCreate,
    ProformaLineResponse,
    ProformaOutstandingRecord,
    ProformaRegisterRecord,
    ProformaResponse,
    ProformaStatusEnum,
    ProformaUpdate,
)
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.settlements.models import Settlement, SettlementDirection, SettlementStatus

#: Orders a proforma may state. A draft is not a deal and a cancelled one has
#: been called off; everything from approval onwards is a real commitment, and
#: a firm may well want to restate a part-delivered order for the balance.
_STATEABLE_ORDER_STATUSES = (
    "APPROVED",
    "PARTIALLY_DELIVERED",
    "DELIVERED",
    "CLOSED",
)


#: The prefix proformas were numbered under until D-SELL-17. A firm's rule still
#: carrying it is moved to the proforma's own on its next proforma.
_SHARED_PREFIX = "PI"


class ProformaService(TransactionalDocumentService):
    """Own the proforma's lifecycle, numbering and snapshot."""

    DOCUMENT = DocumentTypeSpec(
        code="PROFORMA_INVOICE",
        name="Proforma Invoice",
        description="A statement of what an order will be charged",
        category="SALES",
        module="proforma",
        # Its own series, never the tax invoice's. GSTR-1's DOCS section
        # declares the invoice series a firm issued, so a proforma drawing
        # from it would either leave a gap the return cannot explain or put a
        # number in it that was never a supply. And its own prefix: this was
        # "PI", which purchase invoices also use, so one firm held two
        # different documents numbered PI-2026-2027-000004 (D-SELL-17).
        prefix="PF",
        states=(
            DocumentStateSpec("DRAFT", "Draft", 1, allows_edit=True),
            DocumentStateSpec("ISSUED", "Issued", 2),
            DocumentStateSpec("CANCELLED", "Cancelled", 3, is_terminal=True),
        ),
    )

    # ---- reads ---------------------------------------------------------

    def list_proformas(
        self,
        *,
        firm_scope: UUID,
        page: int,
        page_size: int,
        status: str | None = None,
        customer_id: UUID | None = None,
        search: str | None = None,
    ) -> tuple[list[ProformaInvoice], int]:
        """List this firm's proformas, newest first.

        Args:
            firm_scope: The owning firm.
            page: One-based page number.
            page_size: Rows per page.
            status: Narrow to one lifecycle state.
            customer_id: Narrow to one customer.
            search: Match a proforma number.

        Returns:
            The page, and how many rows match in all.

        """
        query = self._scoped(firm_scope)
        if status:
            query = query.where(ProformaInvoice.status == status)
        if customer_id is not None:
            query = query.where(ProformaInvoice.customer_id == customer_id)
        if search:
            query = query.where(
                ProformaInvoice.proforma_number.ilike(f"%{search.strip()}%")
            )
        total = self._session.scalar(select(func.count()).select_from(query.subquery()))
        rows = list(
            self._session.scalars(
                query.order_by(
                    ProformaInvoice.proforma_date.desc(),
                    ProformaInvoice.proforma_number.desc(),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return rows, int(total or 0)

    def get_proforma(self, proforma_id: UUID, *, firm_scope: UUID) -> ProformaInvoice:
        """Return one of this firm's proformas.

        Args:
            proforma_id: The document to read.
            firm_scope: The owning firm.

        Returns:
            The proforma.

        Raises:
            ResourceNotFoundError: If it is not this firm's.

        """
        row = self._session.scalar(
            self._scoped(firm_scope).where(ProformaInvoice.id == proforma_id)
        )
        if row is None:
            raise ResourceNotFoundError("Proforma invoice not found.")
        return row

    def lines_of(self, row: ProformaInvoice) -> list[ProformaInvoiceLine]:
        """Return one proforma's lines, in order."""
        return list(
            self._session.scalars(
                select(ProformaInvoiceLine)
                .where(
                    ProformaInvoiceLine.proforma_invoice_id == row.id,
                    ProformaInvoiceLine.is_deleted.is_(False),
                )
                .order_by(ProformaInvoiceLine.line_number.asc())
            ).all()
        )

    # ---- writes --------------------------------------------------------

    def create_proforma(
        self, data: ProformaCreate, *, firm_id: UUID, actor_id: UUID
    ) -> ProformaInvoice:
        """Raise a proforma stating what one sales order will be charged.

        The lines come off the order as it stands, priced and taxed. They are
        **copied rather than referenced**: the order can be edited afterwards
        -- withdrawing its own approval as it goes -- and a document the
        customer is arranging payment against must not change underneath them.

        Args:
            data: Which order, and the covering terms.
            firm_id: The owning firm.
            actor_id: The user raising it.

        Returns:
            The proforma, in draft.

        Raises:
            ValidationError: If the order cannot be stated.
            ResourceNotFoundError: If the order is not this firm's.

        """
        document_type, numbering_rule = self._ensure_document_setup(
            firm_id=firm_id, actor_id=actor_id
        )
        self._leave_the_shared_prefix(numbering_rule, actor_id=actor_id)
        order = self._stateable_order(data.sales_order_id, firm_id=firm_id)
        lines = self._order_lines(order)
        if not lines:
            raise ValidationError(
                "This order has no lines, so there is nothing to state."
            )
        if data.supersedes_id is not None:
            # Only to say what it replaces; the earlier one is not touched
            # here, because withdrawing it is a decision with its own reason.
            self.get_proforma(data.supersedes_id, firm_scope=firm_id)

        number = self._issue_number(
            numbering_rule,
            typed=data.proforma_number,
            number_column=ProformaInvoice.proforma_number,
            firm_id=firm_id,
            document_date=data.proforma_date,
            actor_id=actor_id,
            branch_code=self._scope_code(order.branch_id),
            company_code=self._company_code(firm_id),
        )

        row = ProformaInvoice(
            firm_id=firm_id,
            customer_id=order.customer_id,
            branch_id=order.branch_id,
            sales_order_id=order.id,
            proforma_number=number.strip().upper(),
            proforma_date=data.proforma_date,
            valid_until=data.valid_until,
            status=ProformaStatus.DRAFT.value,
            customer_reference=data.customer_reference,
            # The order carries no terms of its own, so what the proforma
            # states is what the caller states. Inheriting from a field
            # that does not exist is how a blank ends up on a document
            # somebody presents to a bank.
            payment_terms=data.payment_terms,
            delivery_terms=data.delivery_terms,
            currency_code=order.currency_code,
            remarks=data.remarks,
            supersedes_id=data.supersedes_id,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        self._snapshot_lines(
            row,
            lines,
            charges=quantize_money(order.additional_charges)
            + quantize_money(order.round_off),
            actor_id=actor_id,
        )
        self._flush_or_conflict("A proforma with this number already exists.")

        self._record_lifecycle_event(
            firm_id=firm_id,
            document_type=document_type,
            document_id=row.id,
            document_number=row.proforma_number,
            action="proforma.created",
            from_state=None,
            to_state=ProformaStatus.DRAFT.value,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="proforma.created",
            entity_type="proforma_invoice",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data=self._audit_snapshot(row),
        )
        self._session.commit()
        return row

    def update_proforma(
        self,
        proforma_id: UUID,
        data: ProformaUpdate,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        expected_version: int | None = None,
    ) -> ProformaInvoice:
        """Amend a draft proforma's covering terms.

        Dumped with ``exclude_unset``, so an omitted field is left alone. The
        lines are not editable at all: restating the deal means correcting the
        order and raising a new proforma, not rewriting the statement.

        Args:
            proforma_id: The document to amend.
            data: The fields to change.
            firm_scope: The owning firm.
            actor_id: The user amending it.
            expected_version: The version the client last read.

        Returns:
            The amended proforma.

        Raises:
            ValidationError: If it has already been issued or cancelled.

        """
        row = self.get_proforma(proforma_id, firm_scope=firm_scope)
        assert_version(row.version, expected_version)
        if row.status != ProformaStatus.DRAFT.value:
            raise ValidationError(
                "Only a draft proforma can be changed. Once it has gone to "
                "the customer, raise a replacement instead."
            )
        before = self._audit_snapshot(row)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(row, field, value)
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="proforma.updated",
            entity_type="proforma_invoice",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data=before,
            after_data=self._audit_snapshot(row),
        )
        self._session.commit()
        return row

    def issue_proforma(
        self, proforma_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> ProformaInvoice:
        """Send the proforma to the customer.

        Nothing is posted, and nothing here could post: this document has no
        journal and no receivable to write to. Issuing records that it went
        out and freezes it, because the customer may begin arranging payment
        against the number the moment they have it.

        Args:
            proforma_id: The document to issue.
            firm_scope: The owning firm.
            actor_id: The user issuing it.

        Returns:
            The issued proforma.

        Raises:
            ValidationError: If it is not a draft.

        """
        row = self.get_proforma(proforma_id, firm_scope=firm_scope)
        if row.status != ProformaStatus.DRAFT.value:
            raise ValidationError(f"{row.proforma_number} has already been issued.")
        document_type, _ = self._ensure_document_setup(
            firm_id=firm_scope, actor_id=actor_id
        )
        row.status = ProformaStatus.ISSUED.value
        row.issued_at = utc_now()
        row.updated_by = actor_id
        self._session.flush()
        self._record_lifecycle_event(
            firm_id=firm_scope,
            document_type=document_type,
            document_id=row.id,
            document_number=row.proforma_number,
            action="proforma.issued",
            from_state=ProformaStatus.DRAFT.value,
            to_state=ProformaStatus.ISSUED.value,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="proforma.issued",
            entity_type="proforma_invoice",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"status": ProformaStatus.DRAFT.value},
            after_data=self._audit_snapshot(row),
        )
        self._session.commit()
        return row

    def cancel_proforma(
        self, proforma_id: UUID, *, reason: str, firm_scope: UUID, actor_id: UUID
    ) -> ProformaInvoice:
        """Withdraw a proforma, saying why.

        Nothing is reversed, because nothing was posted. The row stays: the
        customer holds a copy, and a document that vanished leaves them
        holding a number this system cannot explain.

        Args:
            proforma_id: The document to withdraw.
            reason: Why, kept on the record.
            firm_scope: The owning firm.
            actor_id: The user withdrawing it.

        Returns:
            The cancelled proforma.

        Raises:
            ValidationError: If it is already cancelled.

        """
        row = self.get_proforma(proforma_id, firm_scope=firm_scope)
        if row.status == ProformaStatus.CANCELLED.value:
            raise ValidationError(f"{row.proforma_number} is already cancelled.")
        document_type, _ = self._ensure_document_setup(
            firm_id=firm_scope, actor_id=actor_id
        )
        before = self._audit_snapshot(row)
        was = row.status
        row.status = ProformaStatus.CANCELLED.value
        row.cancelled_at = utc_now()
        row.cancel_reason = reason
        row.updated_by = actor_id
        self._session.flush()
        self._record_lifecycle_event(
            firm_id=firm_scope,
            document_type=document_type,
            document_id=row.id,
            document_number=row.proforma_number,
            action="proforma.cancelled",
            from_state=was,
            to_state=ProformaStatus.CANCELLED.value,
            actor_id=actor_id,
            remarks=reason,
        )
        record_audit(
            self._session,
            action="proforma.cancelled",
            entity_type="proforma_invoice",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data=before,
            after_data=self._audit_snapshot(row),
        )
        self._session.commit()
        return row

    # ---- responses -----------------------------------------------------

    def proforma_response(self, row: ProformaInvoice) -> ProformaResponse:
        """Describe one proforma, lines and all."""
        lines = self.lines_of(row)
        products = {
            product.id: product
            for product in self._session.scalars(
                select(Product).where(
                    Product.id.in_({line.product_id for line in lines})
                )
            ).all()
        }
        customer = self._session.get(Customer, row.customer_id)
        order = self._session.get(SalesOrder, row.sales_order_id)
        return ProformaResponse(
            id=row.id,
            proforma_number=row.proforma_number,
            proforma_date=row.proforma_date,
            valid_until=row.valid_until,
            status=row.status,
            customer_id=row.customer_id,
            customer_name=getattr(customer, "name", None),
            branch_id=row.branch_id,
            sales_order_id=row.sales_order_id,
            sales_order_number=getattr(order, "order_number", None),
            customer_reference=row.customer_reference,
            payment_terms=row.payment_terms,
            delivery_terms=row.delivery_terms,
            currency_code=row.currency_code,
            remarks=row.remarks,
            line_discount_total=row.line_discount_total,
            bill_discount_amount=row.bill_discount_amount,
            subtotal=row.subtotal,
            tax_total=row.tax_total,
            other_charges=quantize_money(
                row.grand_total - row.subtotal - row.tax_total
            ),
            grand_total=row.grand_total,
            issued_at=row.issued_at,
            cancelled_at=row.cancelled_at,
            cancel_reason=row.cancel_reason,
            supersedes_id=row.supersedes_id,
            lines=[
                ProformaLineResponse(
                    id=line.id,
                    line_number=line.line_number,
                    product_id=line.product_id,
                    product_code=getattr(products.get(line.product_id), "code", None),
                    product_name=getattr(products.get(line.product_id), "name", None),
                    description=line.description,
                    quantity=line.quantity,
                    free_quantity=line.free_quantity,
                    unit_price=line.unit_price,
                    discount_percent=line.discount_percent,
                    discount_amount=line.discount_amount,
                    bill_discount_amount=line.bill_discount_amount,
                    gross_amount=line.gross_amount,
                    tax_amount=line.tax_amount,
                    net_amount=line.net_amount,
                )
                for line in lines
            ],
            version=row.version,
        )

    # ---- internals -----------------------------------------------------

    def _leave_the_shared_prefix(
        self, rule: DocumentNumberingRule, *, actor_id: UUID
    ) -> None:
        """Move a firm's proforma series off the prefix purchase invoices use.

        Every firm set up before D-SELL-17 has a proforma rule saying "PI",
        written as the default rather than chosen. It moves to the proforma's
        own prefix once: the rule is marked the first time it is looked at,
        so a firm that later sets "PI" on purpose keeps it. The sequence
        carries on, so nothing already issued is renumbered and no new number
        can repeat an old one.
        """
        configuration = dict(rule.configuration or {})
        if configuration.get("own_prefix_checked"):
            return
        configuration["own_prefix_checked"] = True
        rule.configuration = configuration
        if rule.prefix != _SHARED_PREFIX:
            return
        before: dict[str, object] = {"prefix": rule.prefix}
        rule.prefix = self.DOCUMENT.prefix
        rule.updated_by = actor_id
        record_audit(
            self._session,
            action="document_numbering_rule.updated",
            entity_type="document_numbering_rule",
            entity_id=rule.id,
            actor_id=actor_id,
            firm_id=rule.firm_id,
            before_data=before,
            after_data={
                "prefix": rule.prefix,
                "reason": "Proformas number under their own prefix (D-SELL-17).",
            },
        )

    def _scoped(self, firm_scope: UUID) -> Select[tuple[ProformaInvoice]]:
        """Return the base query for one firm's live proformas."""
        return select(ProformaInvoice).where(
            ProformaInvoice.firm_id == firm_scope,
            ProformaInvoice.is_deleted.is_(False),
        )

    def _stateable_order(self, order_id: UUID, *, firm_id: UUID) -> SalesOrder:
        """Return an order a proforma may state.

        Args:
            order_id: The order to state.
            firm_id: The owning firm.

        Returns:
            The order.

        Raises:
            ResourceNotFoundError: If it is not this firm's.
            ValidationError: If it is a draft or has been cancelled.

        """
        order = self._session.scalar(
            select(SalesOrder).where(
                SalesOrder.id == order_id,
                SalesOrder.firm_id == firm_id,
                SalesOrder.is_deleted.is_(False),
            )
        )
        if order is None:
            raise ResourceNotFoundError("Sales order not found.")
        if order.status not in _STATEABLE_ORDER_STATUSES:
            raise ValidationError(
                "Only an approved order can be stated on a proforma. A draft "
                "is not a deal and a cancelled one has been called off."
            )
        return order

    def _order_lines(self, order: SalesOrder) -> list[SalesOrderLine]:
        """Return the order's live lines, in order."""
        return list(
            self._session.scalars(
                select(SalesOrderLine)
                .where(
                    SalesOrderLine.sales_order_id == order.id,
                    SalesOrderLine.is_deleted.is_(False),
                )
                .order_by(SalesOrderLine.line_number.asc())
            ).all()
        )

    def _snapshot_lines(
        self,
        row: ProformaInvoice,
        lines: Sequence[SalesOrderLine],
        *,
        charges: Decimal,
        actor_id: UUID,
    ) -> None:
        """Copy the order's priced lines onto the proforma, and total them.

        The totals are summed from the lines that were copied rather than read
        off the order's header. The two agree today; summing what is actually
        on this document is what keeps them agreeing when a proforma covers
        part of an order, which is the next thing anybody will ask for.

        A line's taxable value carries its share of the order's freight, the
        way the order and the bill both tax it, and the header's other charges
        and round-off reach the total. Both were left out, so a proforma asked
        the customer for less than the order would bill while stating the tax
        on the freight it had dropped (D-SELL-16).
        """
        subtotal = ZERO
        tax_total = ZERO
        line_discounts = ZERO
        bill_discounts = ZERO
        for source in lines:
            gross = quantize_money(source.gross_amount)
            discount = quantize_money(source.discount_amount)
            bill_share = quantize_money(source.bill_discount_amount)
            tax = quantize_money(source.tax_amount)
            freight = quantize_money(source.freight_amount)
            taxable = gross - discount - bill_share + freight
            self._session.add(
                ProformaInvoiceLine(
                    proforma_invoice_id=row.id,
                    firm_id=row.firm_id,
                    line_number=source.line_number,
                    product_id=source.product_id,
                    description=source.description,
                    source_sales_order_line_id=source.id,
                    quantity=quantize_money(source.quantity),
                    free_quantity=quantize_money(source.free_quantity),
                    unit_price=quantize_money(source.unit_price),
                    discount_percent=Decimal(str(source.discount_percent or 0)),
                    discount_amount=discount,
                    bill_discount_amount=bill_share,
                    gross_amount=gross,
                    tax_amount=tax,
                    net_amount=quantize_money(taxable + tax),
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
            subtotal += taxable
            tax_total += tax
            line_discounts += discount
            bill_discounts += bill_share
        row.subtotal = quantize_money(subtotal)
        row.tax_total = quantize_money(tax_total)
        row.line_discount_total = quantize_money(line_discounts)
        row.bill_discount_amount = quantize_money(bill_discounts)
        row.grand_total = quantize_money(subtotal + tax_total + charges)

    @staticmethod
    def _audit_snapshot(row: ProformaInvoice) -> dict[str, object]:
        """Describe a proforma for the audit trail."""
        return {
            "proforma_number": row.proforma_number,
            "status": row.status,
            "sales_order_id": str(row.sales_order_id),
            "grand_total": str(row.grand_total),
            "cancel_reason": row.cancel_reason,
        }

    # ---- reports -------------------------------------------------------

    def register_report(
        self, *, firm_scope: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[ProformaRegisterRecord]:
        """Every proforma raised in the window, newest first; paged in SQL."""
        rows = window.fetch(
            self._session,
            select(ProformaInvoice)
            .where(
                ProformaInvoice.firm_id == firm_scope,
                ProformaInvoice.is_deleted.is_(False),
                *window.dated(ProformaInvoice.proforma_date),
            )
            .order_by(
                ProformaInvoice.proforma_date.desc(),
                ProformaInvoice.created_at.desc(),
                ProformaInvoice.id.desc(),
            ),
        )
        names = self._customer_names({row.customer_id for row in rows})
        orders = self._order_numbers({row.sales_order_id for row in rows})
        records = [
            ProformaRegisterRecord(
                proforma_id=row.id,
                proforma_number=row.proforma_number,
                proforma_date=row.proforma_date,
                valid_until=row.valid_until,
                customer_id=row.customer_id,
                customer_name=names.get(row.customer_id, str(row.customer_id)),
                sales_order_id=row.sales_order_id,
                sales_order_number=orders.get(row.sales_order_id, ""),
                grand_total=row.grand_total,
                status=ProformaStatusEnum(row.status),
            )
            for row in rows
        ]
        return mapped_like(rows, records)

    def outstanding_report(
        self, *, firm_scope: UUID
    ) -> list[ProformaOutstandingRecord]:
        """Issued proformas a customer is still arranging payment against.

        Superseded ones are left out -- a revision replaced them, and a buyer
        holding two figures for one order is the confusion `supersedes_id`
        exists to prevent. So are the ones whose job is done: a proforma is
        never moved after issue (§11.18), so "still arranging payment" is
        read off its order -- posted receipts naming the order that cover
        the proforma's total, or a live tax invoice raised for the order,
        settle it. Every issued proforma ever was listed before, paid and
        billed ones included (D-RPT-11). An expired one is reported with a
        negative `days_to_expiry` rather than dropped: a figure somebody is
        still acting on is exactly the one worth knowing has lapsed.
        """
        superseded = {
            row
            for row in self._session.scalars(
                select(ProformaInvoice.supersedes_id).where(
                    ProformaInvoice.firm_id == firm_scope,
                    ProformaInvoice.is_deleted.is_(False),
                    ProformaInvoice.supersedes_id.is_not(None),
                )
            ).all()
        }
        rows = [
            row
            for row in self._session.scalars(
                select(ProformaInvoice)
                .where(
                    ProformaInvoice.firm_id == firm_scope,
                    ProformaInvoice.is_deleted.is_(False),
                    ProformaInvoice.status == ProformaStatus.ISSUED.value,
                )
                .order_by(ProformaInvoice.proforma_date.asc())
            ).all()
            if row.id not in superseded
        ]
        order_ids = {row.sales_order_id for row in rows}
        received = self._received_against(firm_scope=firm_scope, order_ids=order_ids)
        billed = self._orders_billed(firm_scope=firm_scope, order_ids=order_ids)
        rows = [
            row
            for row in rows
            if row.sales_order_id not in billed
            and received.get(row.sales_order_id, ZERO) < quantize_money(row.grand_total)
        ]
        names = self._customer_names({row.customer_id for row in rows})
        orders = self._orders({row.sales_order_id for row in rows})
        # Today in UTC: everything stored here is UTC, and the server's own
        # date is already tomorrow, or still yesterday, for part of every day.
        today = utc_now().date()
        records: list[ProformaOutstandingRecord] = []
        for row in rows:
            order = orders.get(row.sales_order_id)
            got = received.get(row.sales_order_id, ZERO)
            records.append(
                ProformaOutstandingRecord(
                    proforma_id=row.id,
                    proforma_number=row.proforma_number,
                    proforma_date=row.proforma_date,
                    valid_until=row.valid_until,
                    days_to_expiry=(
                        None
                        if row.valid_until is None
                        else (row.valid_until - today).days
                    ),
                    customer_id=row.customer_id,
                    customer_name=names.get(row.customer_id, str(row.customer_id)),
                    sales_order_number=order.order_number if order else "",
                    sales_order_status=order.status if order else "",
                    grand_total=row.grand_total,
                    received_amount=got,
                    balance_due=quantize_money(row.grand_total) - got,
                )
            )
        return records

    def _received_against(
        self, *, firm_scope: UUID, order_ids: set[UUID]
    ) -> dict[UUID, Decimal]:
        """Sum the posted receipts that name each order, in one read.

        A receipt names the order the money came in against; that is the
        only trace a payment against a proforma leaves, since the proforma
        itself posts nothing.
        """
        if not order_ids:
            return {}
        rows = self._session.execute(
            select(Settlement.sales_order_id, func.sum(Settlement.amount))
            .where(
                Settlement.firm_id == firm_scope,
                Settlement.is_deleted.is_(False),
                Settlement.direction == SettlementDirection.RECEIPT.value,
                Settlement.status == SettlementStatus.POSTED.value,
                Settlement.sales_order_id.in_(list(order_ids)),
            )
            .group_by(Settlement.sales_order_id)
        ).all()
        return {
            order_id: quantize_money(Decimal(str(total)))
            for order_id, total in rows
            if order_id is not None
        }

    def _orders_billed(self, *, firm_scope: UUID, order_ids: set[UUID]) -> set[UUID]:
        """Return the orders a live tax invoice has been raised for.

        Straight from the order, or from a delivery note of the order; a
        cancelled invoice billed nothing. Imported here: the invoice and
        delivery-note modules import this module's neighbours.
        """
        from app.delivery_note.models import DeliveryNote
        from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine

        if not order_ids:
            return set()
        live_line = (
            select(SalesInvoiceLine)
            .join(SalesInvoice, SalesInvoice.id == SalesInvoiceLine.sales_invoice_id)
            .where(
                SalesInvoice.firm_id == firm_scope,
                SalesInvoice.is_deleted.is_(False),
                SalesInvoice.status != "CANCELLED",
                SalesInvoiceLine.is_deleted.is_(False),
            )
        )
        from_orders = {
            row
            for row in self._session.scalars(
                live_line.with_only_columns(SalesInvoiceLine.source_document_id).where(
                    SalesInvoiceLine.source_document_type == "SALES_ORDER",
                    SalesInvoiceLine.source_document_id.in_(list(order_ids)),
                )
            ).all()
        }
        from_notes = {
            row
            for row in self._session.scalars(
                select(DeliveryNote.sales_order_id).where(
                    DeliveryNote.firm_id == firm_scope,
                    DeliveryNote.is_deleted.is_(False),
                    DeliveryNote.sales_order_id.in_(list(order_ids)),
                    DeliveryNote.id.in_(
                        live_line.with_only_columns(
                            SalesInvoiceLine.source_document_id
                        ).where(
                            SalesInvoiceLine.source_document_type == "DELIVERY_NOTE"
                        )
                    ),
                )
            ).all()
        }
        return {row for row in from_orders | from_notes if row is not None}

    def _orders(self, ids: set[UUID]) -> dict[UUID, SalesOrder]:
        """Read the orders named, in one query."""
        if not ids:
            return {}
        return {
            order.id: order
            for order in self._session.scalars(
                select(SalesOrder).where(SalesOrder.id.in_(list(ids)))
            ).all()
        }

    def _customer_names(self, ids: set[UUID]) -> dict[UUID, str]:
        """Read the names in one query rather than one per row."""
        if not ids:
            return {}
        return {
            row.id: row.display_name
            for row in self._session.scalars(
                select(Customer).where(Customer.id.in_(list(ids)))
            ).all()
        }

    def _order_numbers(self, ids: set[UUID]) -> dict[UUID, str]:
        """Read the order numbers in one query."""
        if not ids:
            return {}
        return {
            row.id: row.order_number
            for row in self._session.scalars(
                select(SalesOrder).where(SalesOrder.id.in_(list(ids)))
            ).all()
        }
