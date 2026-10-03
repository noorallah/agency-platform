"""Stock transfer as a document: dispatch, in transit, receive (STK-1, A126).

A numbered transfer from one warehouse to another, the way Zoho's transfer
orders and Tally's delivery-note-to-branch work:

* **Draft** -- lines and both ends; editable, nothing moves.
* **Dispatched** -- every line leaves the source at the moving average and
  sits *in transit* at the destination, still the firm's and still on the
  books. The challan prints from here. Cancelling now brings the goods back.
* **Received** -- the destination says, per line, what arrived and what of it
  was damaged; damaged goods go on the shelf blocked from sale, and what
  never arrived is a shortage written off to the inventory adjustment account
  at the average. A received transfer is final: goods sent back travel on a
  transfer of their own.

Nothing else posts: the firm owns the goods the whole way, and there is one
inventory account. A transfer between branches with their own GSTINs, which
is a sale, is STK-2.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from app.batch_serial.models.batch_serial import BatchRecord
from app.branches.models.branch_warehouse import Warehouse
from app.common.audit.services import record_audit
from app.core.concurrency import assert_version
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.document_framework.services.transactional_document_service import (
    DocumentStateSpec,
    DocumentTypeSpec,
    TransactionalDocumentService,
)
from app.finance.services.document_posting import DocumentPostingService
from app.inventory.models.stock_transfer import StockTransfer, StockTransferLine
from app.inventory.schemas.inventory import InventoryTransactionType
from app.inventory.services.inventory_service import InventoryService
from app.products.models import Product

ZERO = Decimal("0")
QUANTITY = Field(gt=0, max_digits=18, decimal_places=4)


class StockTransferLineWrite(BaseModel):
    """One product to send, in its stock unit."""

    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    batch_id: UUID | None = None
    quantity: Decimal = QUANTITY
    remarks: str | None = Field(default=None, max_length=500)


class StockTransferWrite(BaseModel):
    """A draft transfer: both ends and the lines."""

    model_config = ConfigDict(extra="forbid")

    transfer_date: date
    from_warehouse_id: UUID
    to_warehouse_id: UUID
    vehicle_number: str | None = Field(default=None, max_length=30)
    transporter_name: str | None = Field(default=None, max_length=200)
    remarks: str | None = Field(default=None, max_length=1000)
    lines: list[StockTransferLineWrite] = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def _two_places(self) -> "StockTransferWrite":
        """Refuse a transfer to the warehouse it leaves."""
        if self.from_warehouse_id == self.to_warehouse_id:
            raise ValueError("A transfer goes to a different warehouse.")
        return self


class StockTransferDispatch(BaseModel):
    """The day the goods leave, and how."""

    model_config = ConfigDict(extra="forbid")

    dispatched_on: date | None = None
    vehicle_number: str | None = Field(default=None, max_length=30)
    transporter_name: str | None = Field(default=None, max_length=200)


class StockTransferReceiptLine(BaseModel):
    """What arrived of one line. Received counts damaged goods too."""

    model_config = ConfigDict(extra="forbid")

    line_number: int = Field(ge=1)
    received_quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    damaged_quantity: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )

    @model_validator(mode="after")
    def _damaged_within_received(self) -> "StockTransferReceiptLine":
        """Damaged goods are goods that arrived."""
        if self.damaged_quantity > self.received_quantity:
            raise ValueError("Damaged cannot be more than was received.")
        return self


class StockTransferReceive(BaseModel):
    """The receipt at the destination.

    A line not named arrived in full and in good order, so receiving the
    whole transfer as sent is an empty list.
    """

    model_config = ConfigDict(extra="forbid")

    received_on: date | None = None
    remarks: str | None = Field(default=None, max_length=1000)
    lines: list[StockTransferReceiptLine] = Field(default_factory=list)


class StockTransferCancel(BaseModel):
    """Why a transfer is withdrawn."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=1000)


class StockTransferLineResponse(BaseModel):
    """One line with what became of it."""

    model_config = ConfigDict(extra="forbid")

    line_number: int
    product_id: UUID
    product_code: str
    product_name: str
    batch_id: UUID | None
    batch_number: str | None
    quantity: Decimal
    received_quantity: Decimal | None
    damaged_quantity: Decimal | None
    short_quantity: Decimal | None
    unit_cost: Decimal | None
    remarks: str | None


class StockTransferResponse(BaseModel):
    """One transfer and its lines."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    transfer_number: str
    transfer_date: date
    from_branch_id: UUID
    from_warehouse_id: UUID
    from_warehouse_name: str
    to_branch_id: UUID
    to_warehouse_id: UUID
    to_warehouse_name: str
    status: str
    dispatched_on: date | None
    received_on: date | None
    vehicle_number: str | None
    transporter_name: str | None
    dispatched_value: Decimal
    shortage_value: Decimal
    remarks: str | None
    receipt_remarks: str | None
    cancel_reason: str | None
    version: int
    lines: list[StockTransferLineResponse]


class StockTransferService(TransactionalDocumentService):
    """Draft, dispatch, receive and cancel stock transfers."""

    DOCUMENT = DocumentTypeSpec(
        code="STOCK_TRANSFER",
        name="Stock Transfer",
        description="Goods sent from one of the firm's warehouses to another.",
        category="INVENTORY",
        module="inventory",
        prefix="TO",
        rule_code="STOCK_TRANSFER_DEFAULT",
        rule_name="Stock Transfer Default Numbering",
        states=(
            DocumentStateSpec("DRAFT", "Draft", 10),
            DocumentStateSpec("DISPATCHED", "Dispatched", 20),
            DocumentStateSpec("RECEIVED", "Received", 30, is_terminal=True),
            DocumentStateSpec("CANCELLED", "Cancelled", 90, is_terminal=True),
        ),
    )

    # ---- draft ---------------------------------------------------------

    def create(
        self, data: StockTransferWrite, *, firm_id: UUID, actor_id: UUID
    ) -> StockTransfer:
        """Save a draft transfer and give it its number; commit."""
        source, destination = self._ends(data, firm_id)
        self._check_lines(data.lines, firm_id)
        _, rule = self._ensure_document_setup(firm_id=firm_id, actor_id=actor_id)
        number = self._issue_number(
            rule,
            typed=None,
            number_column=StockTransfer.transfer_number,
            firm_id=firm_id,
            document_date=data.transfer_date,
            actor_id=actor_id,
            branch_code=self._scope_code(source.branch_id),
            company_code=self._company_code(firm_id),
        )
        row = StockTransfer(
            firm_id=firm_id,
            transfer_number=number,
            transfer_date=data.transfer_date,
            from_branch_id=source.branch_id,
            from_warehouse_id=source.id,
            to_branch_id=destination.branch_id,
            to_warehouse_id=destination.id,
            status="DRAFT",
            vehicle_number=data.vehicle_number,
            transporter_name=data.transporter_name,
            remarks=data.remarks,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._flush_or_conflict("Transfer number already exists in this firm.")
        self._write_lines(row, data.lines, actor_id)
        self._audit("stock_transfer.created", row, actor_id)
        self._session.commit()
        return row

    def update(
        self,
        transfer_id: UUID,
        data: StockTransferWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
        expected_version: int | None = None,
    ) -> StockTransfer:
        """Rewrite a draft; commit.

        A draft's lines have nothing downstream -- no movement names them
        until dispatch -- so they are replaced rather than reconciled.
        """
        row = self.get(transfer_id, firm_id=firm_id)
        assert_version(row.version, expected_version)
        if row.status != "DRAFT":
            raise ValidationError("Only a draft transfer can be changed.")
        source, destination = self._ends(data, firm_id)
        self._check_lines(data.lines, firm_id)
        for line in self.lines(row.id):
            self._session.delete(line)
        self._session.flush()
        row.transfer_date = data.transfer_date
        row.from_branch_id = source.branch_id
        row.from_warehouse_id = source.id
        row.to_branch_id = destination.branch_id
        row.to_warehouse_id = destination.id
        row.vehicle_number = data.vehicle_number
        row.transporter_name = data.transporter_name
        row.remarks = data.remarks
        row.updated_by = actor_id
        self._write_lines(row, data.lines, actor_id)
        self._audit("stock_transfer.updated", row, actor_id)
        self._session.commit()
        return row

    # ---- dispatch ------------------------------------------------------

    def dispatch(
        self,
        transfer_id: UUID,
        data: StockTransferDispatch,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> StockTransfer:
        """Send the goods: off the source, in transit at the destination.

        Raises:
            ValidationError: If the transfer is not a draft, or the source
                does not hold a line's quantity free.

        """
        row = self.get(transfer_id, firm_id=firm_id)
        if row.status != "DRAFT":
            raise ValidationError("Only a draft transfer can be dispatched.")
        on = data.dispatched_on or row.transfer_date
        if on < row.transfer_date:
            raise ValidationError("Goods cannot leave before the transfer's date.")
        if data.vehicle_number is not None:
            row.vehicle_number = data.vehicle_number
        if data.transporter_name is not None:
            row.transporter_name = data.transporter_name
        inventory = InventoryService(self._session)
        total = ZERO
        for line in self.lines(row.id):
            out, value = inventory.stage_transfer_leg(
                firm_scope=firm_id,
                branch_id=row.from_branch_id,
                warehouse_id=row.from_warehouse_id,
                product_id=line.product_id,
                batch_id=line.batch_id,
                transaction_type=InventoryTransactionType.TRANSFER_OUT,
                quantity=line.quantity,
                current_delta=-line.quantity,
                reference_number=row.transfer_number,
                transaction_date=on,
                remarks=f"Transfer {row.transfer_number}: dispatched",
                actor_id=actor_id,
                require_available=True,
            )
            unit_cost = (value / line.quantity).quantize(Decimal("0.0001"))
            transit, _ = inventory.stage_transfer_leg(
                firm_scope=firm_id,
                branch_id=row.to_branch_id,
                warehouse_id=row.to_warehouse_id,
                product_id=line.product_id,
                batch_id=line.batch_id,
                transaction_type=InventoryTransactionType.TRANSFER_IN,
                quantity=line.quantity,
                in_transit_delta=line.quantity,
                owned_delta=line.quantity,
                unit_cost=unit_cost,
                reference_number=row.transfer_number,
                transaction_date=on,
                remarks=f"Transfer {row.transfer_number}: in transit",
                actor_id=actor_id,
            )
            line.unit_cost = unit_cost
            line.dispatch_transaction_id = out.id
            line.transit_transaction_id = transit.id
            line.updated_by = actor_id
            total += value
        row.status = "DISPATCHED"
        row.dispatched_on = on
        row.dispatched_value = total
        row.updated_by = actor_id
        self._event(row, "DISPATCH", "DRAFT", "DISPATCHED", actor_id)
        self._audit("stock_transfer.dispatched", row, actor_id)
        self._session.commit()
        return row

    # ---- receive -------------------------------------------------------

    def receive(
        self,
        transfer_id: UUID,
        data: StockTransferReceive,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> StockTransfer:
        """Take the goods in, recording damage and writing off shortage.

        Raises:
            ValidationError: If the transfer is not in transit, a line is
                named twice or not on it, or more arrived than was sent.

        """
        row = self.get(transfer_id, firm_id=firm_id)
        if row.status != "DISPATCHED":
            raise ValidationError("Only a dispatched transfer can be received.")
        on = data.received_on or row.dispatched_on or row.transfer_date
        if row.dispatched_on is not None and on < row.dispatched_on:
            raise ValidationError("Goods cannot arrive before they left.")
        lines = {line.line_number: line for line in self.lines(row.id)}
        told: dict[int, StockTransferReceiptLine] = {}
        for entry in data.lines:
            if entry.line_number not in lines:
                raise ValidationError(
                    f"Line {entry.line_number} is not on this transfer."
                )
            if entry.line_number in told:
                raise ValidationError(f"Line {entry.line_number} is named twice.")
            told[entry.line_number] = entry
        inventory = InventoryService(self._session)
        shortage = ZERO
        for number, line in sorted(lines.items()):
            sent = Decimal(str(line.quantity))
            said = told.get(number)
            received = sent if said is None else said.received_quantity
            damaged = ZERO if said is None else said.damaged_quantity
            if received > sent:
                raise ValidationError(
                    f"Line {number} sent {sent}; {received} cannot have arrived. "
                    "Goods found over the transfer are a stock adjustment."
                )
            short = sent - received
            moved, value = inventory.stage_transfer_leg(
                firm_scope=firm_id,
                branch_id=row.to_branch_id,
                warehouse_id=row.to_warehouse_id,
                product_id=line.product_id,
                batch_id=line.batch_id,
                transaction_type=InventoryTransactionType.TRANSFER_IN,
                quantity=sent,
                in_transit_delta=-sent,
                current_delta=received,
                damaged_delta=damaged,
                # Owned since dispatch; only what never came stops being so.
                owned_delta=-short,
                reference_number=row.transfer_number,
                transaction_date=on,
                remarks=f"Transfer {row.transfer_number}: received",
                actor_id=actor_id,
            )
            line.received_quantity = received
            line.damaged_quantity = damaged
            line.short_quantity = short
            line.receive_transaction_id = moved.id
            line.updated_by = actor_id
            if short > ZERO:
                shortage += value
        row.status = "RECEIVED"
        row.received_on = on
        row.receipt_remarks = data.remarks
        row.shortage_value = shortage
        row.updated_by = actor_id
        if shortage > ZERO:
            DocumentPostingService(self._session).post_stock_adjustment(
                firm_id=firm_id,
                transaction_id=row.id,
                reference_number=row.transfer_number,
                transaction_date=on,
                value_delta=-shortage,
                actor_id=actor_id,
                remarks=f"Shortage in transit on transfer {row.transfer_number}",
            )
        self._event(row, "RECEIVE", "DISPATCHED", "RECEIVED", actor_id)
        self._audit("stock_transfer.received", row, actor_id)
        self._session.commit()
        return row

    # ---- cancel --------------------------------------------------------

    def cancel(
        self, transfer_id: UUID, reason: str, *, firm_id: UUID, actor_id: UUID
    ) -> StockTransfer:
        """Withdraw a draft, or bring dispatched goods back to the source.

        Raises:
            ValidationError: If the transfer was received or cancelled.

        """
        row = self.get(transfer_id, firm_id=firm_id)
        if row.status == "RECEIVED":
            raise ValidationError(
                "A received transfer is final; send the goods back on a "
                "transfer of their own."
            )
        if row.status == "CANCELLED":
            raise ValidationError("This transfer was already cancelled.")
        if not reason.strip():
            raise ValidationError("Say why the transfer is cancelled.")
        was = row.status
        if was == "DISPATCHED":
            inventory = InventoryService(self._session)
            for line in self.lines(row.id):
                # Out of transit first, then back onto the source's shelf.
                for movement in (
                    line.transit_transaction_id,
                    line.dispatch_transaction_id,
                ):
                    if movement is not None:
                        inventory.reverse_transaction(
                            movement,
                            firm_scope=firm_id,
                            actor_id=actor_id,
                            reason=f"Transfer {row.transfer_number} cancelled.",
                        )
        row.status = "CANCELLED"
        row.cancel_reason = reason.strip()
        row.updated_by = actor_id
        self._event(row, "CANCEL", was, "CANCELLED", actor_id, reason.strip())
        self._audit("stock_transfer.cancelled", row, actor_id)
        self._session.commit()
        return row

    # ---- reads ---------------------------------------------------------

    def get(self, transfer_id: UUID, *, firm_id: UUID) -> StockTransfer:
        """Return one of the firm's transfers."""
        row = self._session.get(StockTransfer, transfer_id)
        if row is None or row.is_deleted or row.firm_id != firm_id:
            raise ResourceNotFoundError("Stock transfer not found.")
        return row

    def list_rows(
        self, firm_id: UUID, *, status: str | None = None
    ) -> list[StockTransfer]:
        """Return the firm's transfers, newest first."""
        query = select(StockTransfer).where(
            StockTransfer.firm_id == firm_id, StockTransfer.is_deleted.is_(False)
        )
        if status:
            query = query.where(StockTransfer.status == status.upper())
        return list(
            self._session.scalars(
                query.order_by(
                    StockTransfer.transfer_date.desc(),
                    StockTransfer.transfer_number.desc(),
                    StockTransfer.id.desc(),
                )
            ).all()
        )

    def lines(self, transfer_id: UUID) -> list[StockTransferLine]:
        """Return a transfer's lines in order."""
        return list(
            self._session.scalars(
                select(StockTransferLine)
                .where(
                    StockTransferLine.transfer_id == transfer_id,
                    StockTransferLine.is_deleted.is_(False),
                )
                .order_by(StockTransferLine.line_number.asc())
            ).all()
        )

    def responses(self, rows: list[StockTransfer]) -> list[StockTransferResponse]:
        """Shape transfers with their lines, one read per table."""
        if not rows:
            return []
        lines = list(
            self._session.scalars(
                select(StockTransferLine)
                .where(
                    StockTransferLine.transfer_id.in_([r.id for r in rows]),
                    StockTransferLine.is_deleted.is_(False),
                )
                .order_by(StockTransferLine.line_number.asc())
            ).all()
        )
        product_ids = {line.product_id for line in lines}
        products = (
            {
                p.id: (p.code, p.name)
                for p in self._session.scalars(
                    select(Product).where(Product.id.in_(product_ids))
                ).all()
            }
            if product_ids
            else {}
        )
        batch_ids = {line.batch_id for line in lines if line.batch_id is not None}
        batches: dict[UUID, str] = (
            {
                batch_id: batch_number
                for batch_id, batch_number in self._session.execute(
                    select(BatchRecord.id, BatchRecord.batch_number).where(
                        BatchRecord.id.in_(batch_ids)
                    )
                ).all()
            }
            if batch_ids
            else {}
        )
        warehouse_ids = {r.from_warehouse_id for r in rows} | {
            r.to_warehouse_id for r in rows
        }
        warehouses: dict[UUID, str] = {
            warehouse_id: name
            for warehouse_id, name in self._session.execute(
                select(Warehouse.id, Warehouse.name).where(
                    Warehouse.id.in_(warehouse_ids)
                )
            ).all()
        }
        return [
            StockTransferResponse(
                id=row.id,
                transfer_number=row.transfer_number,
                transfer_date=row.transfer_date,
                from_branch_id=row.from_branch_id,
                from_warehouse_id=row.from_warehouse_id,
                from_warehouse_name=str(warehouses.get(row.from_warehouse_id) or ""),
                to_branch_id=row.to_branch_id,
                to_warehouse_id=row.to_warehouse_id,
                to_warehouse_name=str(warehouses.get(row.to_warehouse_id) or ""),
                status=row.status,
                dispatched_on=row.dispatched_on,
                received_on=row.received_on,
                vehicle_number=row.vehicle_number,
                transporter_name=row.transporter_name,
                dispatched_value=row.dispatched_value,
                shortage_value=row.shortage_value,
                remarks=row.remarks,
                receipt_remarks=row.receipt_remarks,
                cancel_reason=row.cancel_reason,
                version=row.version,
                lines=[
                    StockTransferLineResponse(
                        line_number=line.line_number,
                        product_id=line.product_id,
                        product_code=products.get(line.product_id, ("", ""))[0],
                        product_name=products.get(line.product_id, ("", ""))[1],
                        batch_id=line.batch_id,
                        batch_number=(
                            batches.get(line.batch_id)
                            if line.batch_id is not None
                            else None
                        ),
                        quantity=line.quantity,
                        received_quantity=line.received_quantity,
                        damaged_quantity=line.damaged_quantity,
                        short_quantity=line.short_quantity,
                        unit_cost=line.unit_cost,
                        remarks=line.remarks,
                    )
                    for line in lines
                    if line.transfer_id == row.id
                ],
            )
            for row in rows
        ]

    # ---- print ---------------------------------------------------------

    def render_challan(self, transfer_id: UUID, *, firm_id: UUID) -> tuple[bytes, str]:
        """Draw the delivery challan that travels with the goods.

        Within one GSTIN a transfer is not a supply, so the goods move on a
        delivery challan (CGST rule 55) rather than an invoice. The challan
        carries quantities only; values are the firm's business.

        Returns:
            The PDF bytes and a file name built from the transfer number.

        Raises:
            ValidationError: If the transfer is still a draft or cancelled.

        """
        # Imported here: the print helpers reach the sales invoice renderer,
        # which nothing else in this module needs.
        from app.document_framework.services.letter_pdf import (
            LetterPage,
            LetterPdfRenderer,
            LetterTable,
        )
        from app.document_framework.services.print_support import (
            firm_party,
            load_template,
        )

        row = self.get(transfer_id, firm_id=firm_id)
        if row.status not in ("DISPATCHED", "RECEIVED"):
            raise ValidationError("A challan prints once the goods are dispatched.")
        view = self.responses([row])[0]
        facts = [
            ("Challan number", row.transfer_number),
            ("Date", (row.dispatched_on or row.transfer_date).strftime("%d-%m-%Y")),
            ("From", view.from_warehouse_name),
            ("To", view.to_warehouse_name),
            ("Purpose", "Stock transfer -- not a sale"),
        ]
        if row.vehicle_number:
            facts.append(("Vehicle", row.vehicle_number))
        if row.transporter_name:
            facts.append(("Transporter", row.transporter_name))
        if row.remarks:
            facts.append(("Remarks", row.remarks))
        table = LetterTable(
            heading="Goods",
            columns=("#", "Code", "Item", "Batch", "Quantity"),
            rows=[
                (
                    str(line.line_number),
                    line.product_code,
                    line.product_name,
                    line.batch_number or "",
                    f"{Decimal(str(line.quantity)).normalize():f}",
                )
                for line in view.lines
            ],
            numeric=frozenset({"Quantity"}),
        )
        template = load_template(
            self._session, firm_scope=firm_id, document_type="SALES_INVOICE"
        )
        pdf = LetterPdfRenderer(template.accent_color).render(
            [
                LetterPage(
                    firm=firm_party(firm_id),
                    title="DELIVERY CHALLAN -- STOCK TRANSFER",
                    facts=facts,
                    tables=[table],
                    counter_signatory="Received by",
                )
            ]
        )
        return pdf, f"{row.transfer_number}.pdf".replace("/", "-")

    # ---- helpers -------------------------------------------------------

    def _ends(
        self, data: StockTransferWrite, firm_id: UUID
    ) -> tuple[Warehouse, Warehouse]:
        """Return the source and destination warehouses, both the firm's."""
        found = {
            w.id: w
            for w in self._session.scalars(
                select(Warehouse).where(
                    Warehouse.id.in_([data.from_warehouse_id, data.to_warehouse_id]),
                    Warehouse.firm_id == firm_id,
                    Warehouse.is_deleted.is_(False),
                )
            ).all()
        }
        if data.from_warehouse_id not in found:
            raise ValidationError("The source warehouse is not one of this firm's.")
        if data.to_warehouse_id not in found:
            raise ValidationError(
                "The destination warehouse is not one of this firm's."
            )
        return found[data.from_warehouse_id], found[data.to_warehouse_id]

    def _check_lines(self, lines: list[StockTransferLineWrite], firm_id: UUID) -> None:
        """Refuse a product or batch that is not the firm's."""
        ids = {line.product_id for line in lines}
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
            raise ValidationError("Unknown product(s) on the transfer.")
        batch_ids = {line.batch_id for line in lines if line.batch_id is not None}
        if not batch_ids:
            return
        owners: dict[UUID, UUID] = {
            batch_id: product_id
            for batch_id, product_id in self._session.execute(
                select(BatchRecord.id, BatchRecord.product_id).where(
                    BatchRecord.id.in_(batch_ids),
                    BatchRecord.firm_id == firm_id,
                )
            ).all()
        }
        for line in lines:
            if line.batch_id is not None and owners.get(line.batch_id) != (
                line.product_id
            ):
                raise ValidationError("A batch on the transfer is not that product's.")

    def _write_lines(
        self,
        row: StockTransfer,
        lines: list[StockTransferLineWrite],
        actor_id: UUID,
    ) -> None:
        """Stage the draft's lines, numbered in order."""
        for number, line in enumerate(lines, start=1):
            self._session.add(
                StockTransferLine(
                    transfer_id=row.id,
                    firm_id=row.firm_id,
                    line_number=number,
                    product_id=line.product_id,
                    batch_id=line.batch_id,
                    quantity=line.quantity,
                    remarks=line.remarks,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )

    def _event(
        self,
        row: StockTransfer,
        action: str,
        from_state: str,
        to_state: str,
        actor_id: UUID,
        remarks: str | None = None,
    ) -> None:
        """Put one step on the transfer's timeline."""
        document_type, _ = self._ensure_document_setup(
            firm_id=row.firm_id, actor_id=actor_id
        )
        self._record_lifecycle_event(
            firm_id=row.firm_id,
            document_type=document_type,
            document_id=row.id,
            document_number=row.transfer_number,
            action=action,
            from_state=from_state,
            to_state=to_state,
            actor_id=actor_id,
            remarks=remarks,
        )

    def _audit(self, action: str, row: StockTransfer, actor_id: UUID) -> None:
        """Write one audit row for a transfer."""
        record_audit(
            self._session,
            action=action,
            entity_type="stock_transfer",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            after_data={
                "transfer_number": row.transfer_number,
                "status": row.status,
                "dispatched_value": str(row.dispatched_value),
                "shortage_value": str(row.shortage_value),
            },
        )
