"""Raise the sales documents a firm has chosen not to type itself.

The chain is quotation, sales order, delivery note, invoice, and a firm decides
per stage which of them its people fill in. This is what fills in the rest: a
bill arriving with bare product lines is turned into a sales order, a delivery
note and then the bill, and a bill arriving against an order is given the
delivery note that order never got.

Two things this deliberately does not do. It does not move stock or post to the
ledger itself -- it drives the same services a person would, so goods still
leave at dispatch and cost of goods sold still belongs to the delivery note.
The note it raises is approved and left waiting: the bill's own approval is
what dispatches it, because a draft bill is a proposal and must not ship
anything (D-SELL-13). And it never commits: everything it stages belongs to
the caller's transaction, so a bill that fails leaves no order and no note
behind it. That is the whole reason the `stage_*` methods exist.
"""

from collections.abc import Callable, Sequence
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.batch_serial.services.mrp_ceiling import refuse_above_batch_mrp
from app.branches.models import Branch, Warehouse
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.delivery_note.models import DeliveryNote, DeliveryNoteLine
from app.delivery_note.schemas import (
    DeliveryNoteBatchPick,
    DeliveryNoteCreate,
    DeliveryNoteLineWrite,
)
from app.delivery_note.services.delivery_note_service import DeliveryNoteService
from app.products.models import Product
from app.sales_invoice.schemas import (
    SalesInvoiceCreate,
    SalesInvoiceLineWrite,
    SalesInvoiceSourceType,
    SalesInvoiceSourceWrite,
)
from app.sales_invoice.services.line_units import unit_of_a_bare_line
from app.sales_order.models import SalesOrder, SalesOrderLine, SalesWorkflowSettings
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services.sales_order_service import SalesOrderService
from app.sales_order.services.workflow_settings_service import SalesWorkflowService

ZERO = Decimal("0")

#: Re-prices a bare bill's typed rates once the chain knows where the goods
#: ship from: given the bill, its branch and its warehouse, returns the bill
#: with each typed GST-inclusive rate read back to its pre-tax rate (backlog
#: 64 row 4). The chain owns no tax, so the invoice service supplies it.
InclusiveRates = Callable[[SalesInvoiceCreate, UUID, UUID], SalesInvoiceCreate]


def refuse_coupon_on_documents(data: SalesInvoiceCreate) -> None:
    """Refuse a coupon on a bill of documents already raised (D-SELL-40).

    Their lines are billed at the prices they were raised at, so a coupon
    would change nothing -- and a field that gives money away must not be
    accepted and quietly do nothing.
    """
    if data.coupon_code:
        raise ValidationError(
            "A coupon is applied where the price is set: on the order, or on "
            "a bill typed straight in. This bill continues documents already "
            "priced, so it cannot take one."
        )


class SalesChainService:
    """Synthesise the sales documents a firm's configuration skips."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session
        #: The delivery notes this call raised for the bill, and only those.
        #: The bill stamps itself on them once it exists, and a note is
        #: billable before dispatch only by the bill that raised it -- the
        #: firm's stage being off says nothing about who raised a note
        #: (D-CFG-16).
        self.raised_notes: list[DeliveryNote] = []
        #: The sales orders this call raised for the bill: only a bill of
        #: bare lines raises one. The bill stamps itself on them as it does on
        #: its notes, so cancelling the draft can withdraw the order and give
        #: back what it reserved (D-SELL-54).
        self.raised_orders: list[SalesOrder] = []

    def ensure_invoice_source(
        self,
        data: SalesInvoiceCreate,
        *,
        firm_id: UUID,
        actor_id: UUID,
        inclusive: InclusiveRates | None = None,
    ) -> SalesInvoiceCreate:
        """Return an invoice payload whose every line names a delivery note.

        Unchanged for a firm on the whole chain, which is every firm until one
        turns a stage off -- the bare-line and order-sourced paths below are
        the only ones that write anything.

        ``inclusive`` is applied to a bill of bare lines only -- the one place
        a rate is typed rather than inherited -- before the order is raised,
        so the order, the note and the bill all carry the pre-tax rate.
        """
        settings = SalesWorkflowService(self._session).settings_for(firm_id)
        bare = [line for line in data.lines if line.source_document_line_id is None]
        if not bare:
            refuse_coupon_on_documents(data)
            if settings.delivery_note_stage:
                return data
            return self._note_for_order(data, firm_id=firm_id, actor_id=actor_id)
        if len(bare) != len(data.lines):
            raise ValidationError(
                "An invoice bills either documents already raised or bare "
                "product lines, never a mixture of the two."
            )
        return self._order_and_note(
            data,
            firm_id=firm_id,
            actor_id=actor_id,
            settings=settings,
            inclusive=inclusive,
        )

    def _order_and_note(
        self,
        data: SalesInvoiceCreate,
        *,
        firm_id: UUID,
        actor_id: UUID,
        settings: SalesWorkflowSettings,
        inclusive: InclusiveRates | None = None,
    ) -> SalesInvoiceCreate:
        """Raise the order and the delivery note a bare bill implies."""
        if settings.sales_order_stage or settings.delivery_note_stage:
            raise ValidationError(
                "This firm raises a sales order and a delivery note before it "
                "bills, so an invoice line must name the document it bills."
            )
        if data.customer_id is None:
            raise ValidationError(
                "A bill raised without a source must name a customer."
            )
        branch_id, warehouse_id = self._resolve_place(
            firm_id=firm_id,
            branch_id=data.branch_id or settings.default_branch_id,
            configured_warehouse_id=settings.default_warehouse_id,
        )
        if inclusive is not None:
            data = inclusive(data, branch_id, warehouse_id)
        order = SalesOrderService(self._session).stage_order(
            SalesOrderCreate(
                customer_id=data.customer_id,
                salesman_id=data.salesman_id,
                territory_id=data.territory_id,
                route_id=data.route_id,
                branch_id=branch_id,
                warehouse_id=warehouse_id,
                business_profile_id=data.business_profile_id,
                order_date=data.invoice_date,
                # Where the bill says the goods go; the note and the bill
                # inherit it from here (backlog 67 row 3).
                shipping_address_id=data.shipping_address_id,
                # The bill's own words; the days stay the customer's, so a
                # counter bill falls due exactly as it always did.
                payment_terms=data.payment_terms,
                reference_number=data.reference_number,
                currency_code=data.currency_code,
                exchange_rate=data.exchange_rate,
                remarks=data.remarks,
                coupon_code=data.coupon_code,
                additional_charges=data.additional_charges,
                round_off=data.round_off,
                bill_discount_percent=data.bill_discount_percent,
                bill_discount_amount=data.bill_discount_amount,
                freight_amount=data.freight_amount,
                lines=[
                    SalesOrderLineWrite(
                        line_number=line.line_number,
                        product_id=self._product_of(line),
                        quantity=line.current_invoice_quantity,
                        # None lets the order's offers give free goods; a
                        # typed zero refuses them (D-SELL-41).
                        free_quantity=line.free_quantity,
                        # Whichever field names the unit: a line naming
                        # only `order_uom_id` BOX was sold as pieces
                        # (D-PRC-44).
                        sales_uom_id=unit_of_a_bare_line(
                            self._session,
                            line_number=line.line_number,
                            order_uom_id=line.order_uom_id,
                            invoice_uom_id=line.invoice_uom_id,
                        ),
                        packaging_type_id=line.packaging_type_id,
                        unit_price=line.unit_price,
                        discount_percent=line.discount_percent,
                        discount_amount=line.discount_amount,
                        tax_profile_id=line.tax_profile_id,
                        warehouse_id=line.warehouse_id or warehouse_id,
                        storage_node_id=line.storage_node_id,
                        # A line drawn wholly from one batch it chose holds
                        # that batch, not the earliest: the draft showed its
                        # quantity reserved on a batch it would never ship
                        # (D-SELL-58). Several batches name no one to pin;
                        # the approval below holds each for what was chosen
                        # from it (D-SELL-81).
                        pinned_batch_id=self._one_batch(line),
                        remarks=line.remarks,
                    )
                    for line in data.lines
                ],
            ),
            firm_id=firm_id,
            actor_id=actor_id,
            # The person is raising a bill, so a customer who is not ACTIVE is
            # refused in those words rather than for an order nobody typed.
            raised_as="bill",
            # A line drawn wholly from one batch it chose may take that
            # batch's PTR or PTS (PG-14); several batches name no one rate.
            price_batches={
                line.line_number: batch_id
                for line in data.lines
                if (batch_id := self._one_batch(line)) is not None
            },
        )
        self._refuse_above_chosen_mrp(order, data.lines)
        self.raised_orders.append(order)
        # Checked for licences at the bill's approval, not here (backlog 54).
        SalesOrderService(self._session).stage_approval(
            order.id,
            firm_scope=firm_id,
            actor_id=actor_id,
            check_licences=False,
            # This approval happens at every save of a draft bill, so the
            # offers it priced with are not claimed here: a draft, a held
            # bill and each edit held a live claim on a limited offer. They
            # stay PENDING and the bill's approval claims them (D-SELL-85).
            claim_offers=False,
            # The order line has one batch to pin and a split line has
            # several, so the split is handed to the approval that holds the
            # stock rather than stored: 1 of one batch and 3 of another held
            # all 4 on whichever expired first (D-SELL-81).
            held_batches={
                line.line_number: [
                    (pick.batch_id, pick.quantity) for pick in line.batches
                ]
                for line in data.lines
                if line.batches and self._one_batch(line) is None
            },
        )
        # The order's lines were raised one per bill line, under its number.
        stated = {
            line.line_number: line.serial_ids
            for line in data.lines
            if line.serial_ids is not None
        }
        chosen = {
            line.line_number: line.batches
            for line in data.lines
            if line.batches is not None
        }
        raised_lines = self._session.scalars(
            select(SalesOrderLine).where(
                SalesOrderLine.sales_order_id == order.id,
                SalesOrderLine.is_deleted.is_(False),
            )
        ).all()
        serials = {
            line.id: stated[line.line_number]
            for line in raised_lines
            if line.line_number in stated
        }
        batches = {
            line.id: chosen[line.line_number]
            for line in raised_lines
            if line.line_number in chosen
        }
        return self._raise_and_rebind(
            data,
            order=order,
            quantities=None,
            serials=serials,
            batches=batches,
            firm_id=firm_id,
            actor_id=actor_id,
        )

    def _note_for_order(
        self, data: SalesInvoiceCreate, *, firm_id: UUID, actor_id: UUID
    ) -> SalesInvoiceCreate:
        """Dispatch the order a bill names, for a firm that types no notes.

        The order is the firm's own document here -- somebody raised and
        approved it -- so only the note is missing, and it ships exactly what
        the bill charges for.
        """
        order_ids = {
            line.source_document_id
            for line in data.lines
            if line.source_document_type == SalesInvoiceSourceType.SALES_ORDER
        }
        if not order_ids:
            return data
        if len(order_ids) > 1:
            raise ValidationError(
                "A bill that dispatches its own goods bills one sales order at "
                "a time."
            )
        order = self._session.scalar(
            select(SalesOrder).where(
                SalesOrder.id == order_ids.pop(),
                SalesOrder.firm_id == firm_id,
                SalesOrder.is_deleted.is_(False),
            )
        )
        if order is None:
            raise ResourceNotFoundError("Sales order not found.")
        quantities = {
            line.source_document_line_id: line.current_invoice_quantity
            for line in data.lines
            if line.source_document_line_id is not None
        }
        serials = {
            line.source_document_line_id: line.serial_ids
            for line in data.lines
            if line.source_document_line_id is not None and line.serial_ids is not None
        }
        batches = {
            line.source_document_line_id: line.batches
            for line in data.lines
            if line.source_document_line_id is not None and line.batches is not None
        }
        return self._raise_and_rebind(
            data,
            order=order,
            quantities=quantities,
            serials=serials,
            batches=batches,
            firm_id=firm_id,
            actor_id=actor_id,
        )

    def _raise_and_rebind(
        self,
        data: SalesInvoiceCreate,
        *,
        order: SalesOrder,
        quantities: dict[UUID, Decimal] | None,
        serials: dict[UUID, list[UUID]],
        firm_id: UUID,
        actor_id: UUID,
        batches: dict[UUID, list[DeliveryNoteBatchPick]] | None = None,
    ) -> SalesInvoiceCreate:
        """Raise and approve the note, then bill it instead.

        The note is not dispatched here. Saving a draft bill used to ship its
        goods and post their cost there and then, so a draft cancelled a
        minute later left the stock out and the order DELIVERED with nothing
        billed (D-SELL-13, driven 2026-09-19). `SalesInvoiceService` dispatches
        it when the bill is approved, and cancels it if the draft is.

        `quantities` names how much of each order line to ship; None ships the
        whole order, which is what a bare bill means. `serials` names the units
        each order line ships, for a serial-tracked product; `batches` the
        batches a counter bill chose for a line (backlog 79 row 2).
        """
        order_lines = list(
            self._session.scalars(
                select(SalesOrderLine)
                .where(
                    SalesOrderLine.sales_order_id == order.id,
                    SalesOrderLine.is_deleted.is_(False),
                )
                .order_by(SalesOrderLine.line_number.asc())
            ).all()
        )
        self._refuse_serialised(
            [
                line
                for line in order_lines
                if self._ships(line, quantities) and line.id not in serials
            ]
        )
        notes = DeliveryNoteService(self._session)
        note = notes.stage_note(
            DeliveryNoteCreate(
                sales_order_id=order.id,
                delivery_date=data.invoice_date,
                shipping_address_id=data.shipping_address_id,
                remarks=data.remarks,
                additional_charges=data.additional_charges,
                round_off=data.round_off,
                bill_discount_percent=data.bill_discount_percent,
                bill_discount_amount=data.bill_discount_amount,
                freight_amount=data.freight_amount,
                lines=[
                    self._note_line(
                        line,
                        quantities,
                        serials.get(line.id),
                        (batches or {}).get(line.id),
                    )
                    for line in order_lines
                    if self._ships(line, quantities)
                ],
            ),
            firm_id=firm_id,
            actor_id=actor_id,
        )
        notes.stage_approval(
            note.id, firm_scope=firm_id, actor_id=actor_id, check_licences=False
        )
        self.raised_notes.append(note)
        return self._rebind(data, note=note)

    def _refuse_serialised(self, lines: list[SalesOrderLine]) -> None:
        """Refuse a serial-tracked line whose bill names no units.

        The document that moves the stock is where the units are named -- the
        way Tally, SAP Business One and Odoo ask for serials on whichever
        document issues the goods -- and dispatch refuses a serial-tracked
        line without one per unit (D-STK-4). A bill that dispatches its own
        goods names them in each line's ``serial_ids`` and the chain hands
        them to the note; one that names none is refused by name here, before
        anything is staged, rather than at dispatch with a sentence about a
        note nobody typed.
        """
        ids = {line.product_id for line in lines}
        if not ids:
            return
        serialised = sorted(
            product.code
            for product in self._session.scalars(
                select(Product).where(Product.id.in_(ids), Product.track_serial)
            ).all()
        )
        if serialised:
            raise ValidationError(
                f"{', '.join(serialised)} is serial-tracked: name the serial "
                "numbers going out on the bill line, or raise a delivery note "
                "for the order, pick them there, and bill that note."
            )

    def _note_line(
        self,
        line: SalesOrderLine,
        quantities: dict[UUID, Decimal] | None,
        serial_ids: list[UUID] | None = None,
        batches: list[DeliveryNoteBatchPick] | None = None,
    ) -> DeliveryNoteLineWrite:
        """Ship one order line, carrying the deal the order already struck.

        The line says nothing about a discount, so the note inherits the
        order line's by the share it ships, as a note a person types does
        (`DeliveryNoteService._line_discount`). It used to state the order
        line's whole ``discount_amount`` whatever part was billed, and an
        amount stated beats everything: an order of 10 with 100.00 off the
        line, billed 4 and then 6 with the note stage off, took the 100.00
        off both bills and under-billed the customer 118.00 (D-PRC-22).
        """
        shipping = self._shipping(line, quantities)
        # A bill of the whole order ships its free goods whole. A part bill
        # says nothing, so the note ships the share that goes with the share
        # taken, in whole units, the last part taking what is left (D-PRC-4);
        # pro-rated here it shipped 0.5 of a gift.
        free = line.free_quantity if quantities is None else None
        return DeliveryNoteLineWrite(
            sales_order_line_id=line.id,
            line_number=line.line_number,
            description=line.description,
            current_delivery_quantity=shipping,
            free_quantity=free,
            unit_price=line.unit_price,
            tax_profile_id=line.tax_profile_id,
            packaging_type_id=line.packaging_type_id,
            sales_uom_id=line.sales_uom_id,
            inventory_uom_id=line.inventory_uom_id,
            warehouse_id=line.warehouse_id,
            storage_node_id=line.storage_node_id,
            remarks=line.remarks,
            serial_ids=serial_ids,
            batches=batches,
        )

    @staticmethod
    def _shipping(
        line: SalesOrderLine, quantities: dict[UUID, Decimal] | None
    ) -> Decimal:
        """Report how much of one order line this dispatch carries."""
        if quantities is None:
            return line.quantity
        return quantities.get(line.id, ZERO)

    @classmethod
    def _ships(
        cls, line: SalesOrderLine, quantities: dict[UUID, Decimal] | None
    ) -> bool:
        """Say whether this dispatch carries anything of one order line.

        A line whose whole content is a gift charges for nothing and still
        ships: it goes whenever the bill takes the whole order or names the
        line. Judged on the charged quantity alone it was left off the note,
        and a bill of nothing but free goods raised a note with no lines
        (D-SELL-53).
        """
        if cls._shipping(line, quantities) > ZERO:
            return True
        return line.quantity <= ZERO < line.free_quantity and (
            quantities is None or line.id in quantities
        )

    def _rebind(
        self, data: SalesInvoiceCreate, *, note: DeliveryNote
    ) -> SalesInvoiceCreate:
        """Point the bill at the note that now holds the goods.

        Billing is capped on `current_delivery_quantity` -- what the customer
        is charged for -- and never on `delivered_quantity`, which has the free
        goods folded into it and is measured in inventory units.
        """
        note_lines = list(
            self._session.scalars(
                select(DeliveryNoteLine)
                .where(
                    DeliveryNoteLine.delivery_note_id == note.id,
                    DeliveryNoteLine.is_deleted.is_(False),
                )
                .order_by(DeliveryNoteLine.line_number.asc())
            ).all()
        )
        lines = [
            SalesInvoiceLineWrite(
                source_document_type=SalesInvoiceSourceType.DELIVERY_NOTE,
                source_document_id=note.id,
                source_document_line_id=note_line.id,
                line_number=note_line.line_number,
                current_invoice_quantity=note_line.current_delivery_quantity,
                unit_price=note_line.unit_price,
                # Left unstated so the invoice inherits the note's free goods
                # and its discount pro-rata, the same way any other bill does.
                tax_profile_id=note_line.tax_profile_id,
                packaging_type_id=note_line.packaging_type_id,
                invoice_uom_id=note_line.sales_uom_id,
                warehouse_id=note_line.warehouse_id,
                storage_node_id=note_line.storage_node_id,
                remarks=note_line.remarks,
            )
            for note_line in note_lines
        ]
        return data.model_copy(
            update={
                "source_documents": [
                    SalesInvoiceSourceWrite(
                        source_document_type=SalesInvoiceSourceType.DELIVERY_NOTE,
                        source_document_id=note.id,
                    )
                ],
                "lines": lines,
                # Spent on the order, which priced the lines this bill now
                # continues; the bill itself carries no coupon.
                "coupon_code": None,
            }
        )

    def _refuse_above_chosen_mrp(
        self, order: SalesOrder, lines: Sequence[SalesInvoiceLineWrite]
    ) -> None:
        """Hold a line drawn from several chosen batches to the lowest MRP.

        A line drawn wholly from one batch is pinned to it on the order, and
        the order judges its own pinned lines as it saves them. One that
        chose two or more names no batch to pin, so it is judged here, on the
        order line just priced, at the save of the bill rather than at its
        approval (D-PRC-7).

        Raises:
            ValidationError: Naming the line, the rate and the MRP.

        """
        chosen = {
            line.line_number: [pick.batch_id for pick in line.batches or []]
            for line in lines
            if len({pick.batch_id for pick in line.batches or []}) > 1
        }
        if not chosen:
            return
        for line in self._session.scalars(
            select(SalesOrderLine)
            .where(
                SalesOrderLine.sales_order_id == order.id,
                SalesOrderLine.is_deleted.is_(False),
                SalesOrderLine.line_number.in_(chosen),
            )
            .order_by(SalesOrderLine.line_number)
        ):
            refuse_above_batch_mrp(
                self._session,
                line_number=line.line_number,
                product_id=line.product_id,
                batch_ids=chosen[line.line_number],
                paid=Decimal(str(line.net_amount))
                - Decimal(str(line.freight_amount or 0)),
                quantity=Decimal(str(line.quantity or 0)),
                stock_units_per_unit=line.conversion_factor,
            )

    @staticmethod
    def _one_batch(line: SalesInvoiceLineWrite) -> UUID | None:
        """Return the batch a bare line is drawn wholly from, if it chose one."""
        if not line.batches:
            return None
        chosen = {pick.batch_id for pick in line.batches}
        return chosen.pop() if len(chosen) == 1 else None

    @staticmethod
    def _product_of(line: SalesInvoiceLineWrite) -> UUID:
        """Return the product a bare line names."""
        if line.product_id is None:
            raise ValidationError("A bare invoice line must name a product.")
        return line.product_id

    def _resolve_place(
        self,
        *,
        firm_id: UUID,
        branch_id: UUID | None,
        configured_warehouse_id: UUID | None,
    ) -> tuple[UUID, UUID]:
        """Decide where a synthesised sale ships from.

        The request wins, then the firm's configured defaults, then the branch
        and warehouse the firm marked default. Dispatch refuses a line with no
        warehouse, and a firm whose delivery-note stage is automatic never sees
        a field to type one into -- so failing here, by name, beats failing
        three documents later with a message about a note the user never saw.

        The configured warehouse is the default *branch's*: a bill that names
        another branch ships from that branch's own default, not from a
        warehouse the order would then refuse as outside its branch
        (D-CFG-14).
        """
        if branch_id is None:
            branch_id = self._session.scalar(
                select(Branch.id).where(
                    Branch.firm_id == firm_id,
                    Branch.is_default.is_(True),
                    Branch.is_deleted.is_(False),
                )
            )
        if branch_id is None:
            raise ValidationError(
                "This firm has no default branch, so a bill cannot decide "
                "where its goods ship from."
            )
        warehouse_id: UUID | None = None
        if configured_warehouse_id is not None:
            warehouse_id = self._session.scalar(
                select(Warehouse.id).where(
                    Warehouse.id == configured_warehouse_id,
                    Warehouse.branch_id == branch_id,
                    Warehouse.is_deleted.is_(False),
                )
            )
        if warehouse_id is None:
            warehouse_id = self._session.scalar(
                select(Warehouse.id).where(
                    Warehouse.branch_id == branch_id,
                    Warehouse.is_default.is_(True),
                    Warehouse.is_deleted.is_(False),
                )
            )
        if warehouse_id is None:
            raise ValidationError(
                "This branch has no default warehouse, so a bill cannot decide "
                "where its goods ship from."
            )
        return branch_id, warehouse_id
