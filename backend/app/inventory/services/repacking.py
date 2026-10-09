"""Repacking and bulk breaking (STK-4, decision A114).

One document, one transaction: every consume line leaves stock at the
product's moving average; the value consumed, less the wastage share, is
spread over the produce lines in proportion to what each is worth at its
purchase price (or its quantity, where none has a price) and arrives at that
cost; the wastage is written off to the inventory adjustment account. With
no wastage the books do not move -- inventory became inventory. Cancelling
reverses every movement and the wastage journal.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from app.batch_serial.services.batch_serial_service import BatchSerialService
from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.pricing import apportion
from app.document_framework.services.transactional_document_service import (
    DocumentStateSpec,
    DocumentTypeSpec,
    TransactionalDocumentService,
)
from app.finance.services.document_posting import (
    DocumentPostingService,
    assert_stock_date_in_open_period,
)
from app.inventory.models.repack import Repack, RepackLine
from app.inventory.services.inventory_service import InventoryService
from app.products.models import Product
from app.products.services.stockless import assert_held_as_stock

ZERO = Decimal("0")


class RepackLineWrite(BaseModel):
    """One product consumed or produced."""

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(pattern="^(CONSUME|PRODUCE)$")
    product_id: UUID
    batch_id: UUID | None = None
    #: The batch a produce line goes into, by number: found if the product
    #: has one of that number, opened with these dates if it has not.
    batch_number: str | None = Field(default=None, min_length=1, max_length=100)
    manufacturing_date: date | None = None
    expiry_date: date | None = None
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)

    @model_validator(mode="after")
    def _one_way_to_name_a_batch(self) -> "RepackLineWrite":
        """Keep the batch typed by number to the goods coming out."""
        typed = (self.batch_number, self.manufacturing_date, self.expiry_date)
        if self.kind == "CONSUME" and any(value is not None for value in typed):
            raise ValueError(
                "A consume line names a batch that is already held, by its id; "
                "only a produce line opens one by number."
            )
        if self.batch_id is not None and any(value is not None for value in typed):
            raise ValueError(
                "Name the batch by its id or by its number and dates, not both."
            )
        if self.batch_number is None and any(value is not None for value in typed):
            raise ValueError("A batch's dates need its number.")
        return self


class RepackWrite(BaseModel):
    """A repack: at least one line consumed and one produced."""

    model_config = ConfigDict(extra="forbid")

    repack_date: date
    branch_id: UUID
    warehouse_id: UUID
    wastage_percent: Decimal = Field(
        default=Decimal("0"), ge=0, lt=100, max_digits=7, decimal_places=4
    )
    remarks: str | None = Field(default=None, max_length=1000)
    lines: list[RepackLineWrite] = Field(min_length=2, max_length=200)

    @model_validator(mode="after")
    def _both_sides(self) -> "RepackWrite":
        """Require goods going in and goods coming out."""
        kinds = {line.kind for line in self.lines}
        if kinds != {"CONSUME", "PRODUCE"}:
            raise ValueError("A repack consumes at least one line and produces one.")
        return self


class RepackCancel(BaseModel):
    """Why a repack is reversed."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=1000)


class RepackLineResponse(BaseModel):
    """One line as posted."""

    model_config = ConfigDict(extra="forbid")

    line_number: int
    kind: str
    product_id: UUID
    product_code: str
    product_name: str
    batch_id: UUID | None
    quantity: Decimal
    value: Decimal


class RepackResponse(BaseModel):
    """One repack and its lines."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    repack_number: str
    repack_date: date
    branch_id: UUID
    warehouse_id: UUID
    wastage_percent: Decimal
    consumed_value: Decimal
    wastage_value: Decimal
    status: str
    remarks: str | None
    cancel_reason: str | None
    version: int
    lines: list[RepackLineResponse]


class RepackService(TransactionalDocumentService):
    """Post and cancel repacks."""

    DOCUMENT = DocumentTypeSpec(
        code="REPACK",
        name="Repack",
        description="One product broken or repacked into others.",
        category="INVENTORY",
        module="inventory",
        prefix="RPK",
        rule_code="REPACK_DEFAULT",
        rule_name="Repack Default Numbering",
        states=(
            DocumentStateSpec("POSTED", "Posted", 10),
            DocumentStateSpec("CANCELLED", "Cancelled", 90, is_terminal=True),
        ),
    )

    def post(self, data: RepackWrite, *, firm_id: UUID, actor_id: UUID) -> Repack:
        """Consume, produce and write off the wastage in one commit.

        Raises:
            ValidationError: If a product is not the firm's, or stock is short.

        """
        row = self.stage_post(data, firm_id=firm_id, actor_id=actor_id)
        self._session.commit()
        return row

    def stage_post(self, data: RepackWrite, *, firm_id: UUID, actor_id: UUID) -> Repack:
        """Post a repack without committing, for a caller composing more.

        Kits are assembled this way when a delivery note ships more than is
        assembled (STK-15): the components leave in the dispatch's own
        transaction.

        Raises:
            ValidationError: If a product is not the firm's, or stock is short.

        """
        on = data.repack_date
        assert_stock_date_in_open_period(self._session, firm_id, on, what="A repack")
        products = {
            p.id: p
            for p in self._session.scalars(
                select(Product).where(
                    Product.id.in_({line.product_id for line in data.lines}),
                    Product.firm_id == firm_id,
                    Product.is_deleted.is_(False),
                )
            ).all()
        }
        missing = {line.product_id for line in data.lines} - set(products)
        if missing:
            raise ValidationError("Unknown product(s) on the repack.")
        for line in data.lines:
            if line.kind == "PRODUCE":
                assert_held_as_stock(products[line.product_id])
        inventory = InventoryService(self._session)
        lines = self._lines_by_batch(
            data, products, inventory, firm_id=firm_id, actor_id=actor_id
        )
        _, rule = self._ensure_document_setup(firm_id=firm_id, actor_id=actor_id)
        number = self._issue_number(
            rule,
            typed=None,
            number_column=Repack.repack_number,
            firm_id=firm_id,
            document_date=on,
            actor_id=actor_id,
            branch_code=self._scope_code(data.branch_id),
            company_code=self._company_code(firm_id),
        )
        row = Repack(
            firm_id=firm_id,
            repack_number=number,
            repack_date=on,
            branch_id=data.branch_id,
            warehouse_id=data.warehouse_id,
            wastage_percent=data.wastage_percent,
            status="POSTED",
            remarks=data.remarks,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._flush_or_conflict("Repack number already exists in this firm.")
        consumed = ZERO
        written: list[RepackLine] = []
        for number_on_line, line in enumerate(lines, start=1):
            if line.kind != "CONSUME":
                continue
            transaction, value = inventory.stage_repack_movement(
                firm_scope=firm_id,
                branch_id=data.branch_id,
                warehouse_id=data.warehouse_id,
                product_id=line.product_id,
                batch_id=line.batch_id,
                quantity=-line.quantity,
                unit_cost=None,
                reference_number=number,
                transaction_date=on,
                remarks=f"Repack {number}: consumed",
                actor_id=actor_id,
            )
            consumed += abs(value)
            written.append(
                self._line(
                    row, number_on_line, line, abs(value), transaction.id, actor_id
                )
            )
        wastage = (consumed * data.wastage_percent / Decimal("100")).quantize(
            Decimal("0.0001")
        )
        carried = consumed - wastage
        produced = [
            (number_on_line, line)
            for number_on_line, line in enumerate(lines, start=1)
            if line.kind == "PRODUCE"
        ]
        weights = [
            line.quantity * Decimal(str(products[line.product_id].purchase_price or 0))
            for _, line in produced
        ]
        if not any(weight > ZERO for weight in weights):
            weights = [line.quantity for _, line in produced]
        shares = apportion(carried, weights)
        for (number_on_line, line), share in zip(produced, shares, strict=True):
            transaction, _ = inventory.stage_repack_movement(
                firm_scope=firm_id,
                branch_id=data.branch_id,
                warehouse_id=data.warehouse_id,
                product_id=line.product_id,
                batch_id=line.batch_id,
                quantity=line.quantity,
                unit_cost=(share / line.quantity).quantize(Decimal("0.0001")),
                reference_number=number,
                transaction_date=on,
                remarks=f"Repack {number}: produced",
                actor_id=actor_id,
            )
            written.append(
                self._line(row, number_on_line, line, share, transaction.id, actor_id)
            )
        row.consumed_value = consumed
        row.wastage_value = wastage
        if wastage > ZERO:
            DocumentPostingService(self._session).post_stock_adjustment(
                firm_id=firm_id,
                transaction_id=row.id,
                reference_number=number,
                transaction_date=on,
                value_delta=-wastage,
                actor_id=actor_id,
                remarks=f"Wastage on repack {number}",
            )
        self._audit("repack.posted", row, actor_id)
        return row

    def cancel(
        self, repack_id: UUID, reason: str, *, firm_id: UUID, actor_id: UUID
    ) -> Repack:
        """Reverse every movement and the wastage journal; commit."""
        row = self.get(repack_id, firm_id=firm_id)
        if row.status != "POSTED":
            raise ValidationError("This repack was already cancelled.")
        if not reason.strip():
            raise ValidationError("Say why the repack is cancelled.")
        inventory = InventoryService(self._session)
        # Produced goods go back first, so they are there to take back.
        for line in sorted(self.lines(row.id), key=lambda line: line.kind != "PRODUCE"):
            if line.inventory_transaction_id is not None:
                inventory.reverse_transaction(
                    line.inventory_transaction_id,
                    firm_scope=firm_id,
                    actor_id=actor_id,
                    reason=f"Repack {row.repack_number} cancelled.",
                )
        if Decimal(str(row.wastage_value)) > ZERO:
            DocumentPostingService(self._session).post_stock_adjustment(
                firm_id=firm_id,
                transaction_id=row.id,
                reference_number=f"{row.repack_number}-REV",
                transaction_date=row.repack_date,
                value_delta=Decimal(str(row.wastage_value)),
                actor_id=actor_id,
                remarks=f"Repack {row.repack_number} cancelled",
            )
        row.status = "CANCELLED"
        row.cancel_reason = reason.strip()
        row.updated_by = actor_id
        self._audit("repack.cancelled", row, actor_id)
        self._session.commit()
        return row

    def get(self, repack_id: UUID, *, firm_id: UUID) -> Repack:
        """Return one of the firm's repacks."""
        row = self._session.get(Repack, repack_id)
        if row is None or row.is_deleted or row.firm_id != firm_id:
            raise ResourceNotFoundError("Repack not found.")
        return row

    def list_rows(self, firm_id: UUID) -> list[Repack]:
        """Return the firm's repacks, newest first."""
        return list(
            self._session.scalars(
                select(Repack)
                .where(Repack.firm_id == firm_id, Repack.is_deleted.is_(False))
                .order_by(Repack.repack_date.desc(), Repack.repack_number.desc())
            ).all()
        )

    def lines(self, repack_id: UUID) -> list[RepackLine]:
        """Return a repack's lines in order."""
        return list(
            self._session.scalars(
                select(RepackLine)
                .where(RepackLine.repack_id == repack_id)
                .order_by(RepackLine.line_number.asc())
            ).all()
        )

    def responses(self, rows: list[Repack]) -> list[RepackResponse]:
        """Shape repacks with their lines, one read per table."""
        if not rows:
            return []
        lines = list(
            self._session.scalars(
                select(RepackLine)
                .where(RepackLine.repack_id.in_([r.id for r in rows]))
                .order_by(RepackLine.line_number.asc())
            ).all()
        )
        ids = {line.product_id for line in lines}
        products = (
            {
                p.id: p
                for p in self._session.scalars(
                    select(Product).where(Product.id.in_(ids))
                ).all()
            }
            if ids
            else {}
        )
        return [
            RepackResponse(
                id=row.id,
                repack_number=row.repack_number,
                repack_date=row.repack_date,
                branch_id=row.branch_id,
                warehouse_id=row.warehouse_id,
                wastage_percent=row.wastage_percent,
                consumed_value=row.consumed_value,
                wastage_value=row.wastage_value,
                status=row.status,
                remarks=row.remarks,
                cancel_reason=row.cancel_reason,
                version=row.version,
                lines=[
                    RepackLineResponse(
                        line_number=line.line_number,
                        kind=line.kind,
                        product_id=line.product_id,
                        product_code=(
                            products[line.product_id].code
                            if line.product_id in products
                            else ""
                        ),
                        product_name=(
                            products[line.product_id].name
                            if line.product_id in products
                            else ""
                        ),
                        batch_id=line.batch_id,
                        quantity=line.quantity,
                        value=line.value,
                    )
                    for line in lines
                    if line.repack_id == row.id
                ],
            )
            for row in rows
        ]

    def _lines_by_batch(
        self,
        data: RepackWrite,
        products: dict[UUID, Product],
        inventory: InventoryService,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> list[RepackLineWrite]:
        """Return the lines as they are posted: one per batch drawn from.

        A product held in batches is several stock rows, and a consume line
        naming none of them was read against the row with no batch: a kit
        with a batch-tracked part was refused with "free 0" while the goods
        stood on the shelf (D-STK-51). Such a line is drawn the way a
        dispatch is, earliest expiry first among batches in date, and is
        written as one line per batch so a cancel puts each back where it
        came from.

        A serial-tracked product is refused on either side. A repack moves a
        quantity and has nowhere to name units, so the stock moved while
        every unit went on reading AVAILABLE (D-STK-52).

        A produce line of a batch-tracked product names the batch it goes
        into, by id or by number. With neither the goods landed on the stock
        row with no batch: a medicine on hand with no expiry, sold last and
        never short-dated (D-STK-53). A number is resolved the way a goods
        receipt resolves one, so a new batch is held to the same dates.

        Raises:
            ValidationError: If a line names a serial-tracked product, the
                batches do not hold what a consume line asks for, or a
                produce line of a batch-tracked product names no batch.

        """
        tracked = sorted(
            {
                products[line.product_id].code
                for line in data.lines
                if products[line.product_id].track_serial
            }
        )
        if tracked:
            raise ValidationError(
                ", ".join(tracked)
                + (" is" if len(tracked) == 1 else " are")
                + " tracked by serial number, and a repack moves a quantity "
                "without naming units. Move the units as themselves: a "
                "transfer, a sale or a write-off names each one."
            )
        lines: list[RepackLineWrite] = []
        for line in data.lines:
            product = products[line.product_id]
            if line.kind == "PRODUCE":
                lines.append(
                    self._produced_into_a_batch(
                        data, line, product, firm_id=firm_id, actor_id=actor_id
                    )
                )
                continue
            if (
                line.kind != "CONSUME"
                or line.batch_id is not None
                or not product.track_batch
            ):
                lines.append(line)
                continue
            for batch_id, quantity in inventory.allocate_for_repack(
                firm_scope=firm_id,
                branch_id=data.branch_id,
                warehouse_id=data.warehouse_id,
                product=product,
                quantity=line.quantity,
                as_of=data.repack_date,
            ):
                lines.append(
                    line.model_copy(update={"batch_id": batch_id, "quantity": quantity})
                )
        return lines

    def _produced_into_a_batch(
        self,
        data: RepackWrite,
        line: RepackLineWrite,
        product: Product,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> RepackLineWrite:
        """Return a produce line naming its batch by id (D-STK-53).

        Raises:
            ValidationError: If the product is kept in batches and the line
                names none, or names one for a product that is not.

        """
        if line.batch_number is None:
            if product.track_batch and line.batch_id is None:
                raise ValidationError(
                    f"{product.code} - {product.name} is kept in batches. "
                    "Name the batch the repacked goods go into: one it "
                    "already has, or a new number with its dates."
                )
            return line
        if not product.track_batch:
            raise ValidationError(
                f"{product.code} - {product.name} is not kept in batches, "
                "so the repacked goods cannot go into one."
            )
        batch = BatchSerialService(self._session).resolve_for_receipt(
            firm_scope=firm_id,
            actor_id=actor_id,
            product_id=product.id,
            batch_number=line.batch_number,
            branch_id=data.branch_id,
            warehouse_id=data.warehouse_id,
            expiry_date=line.expiry_date,
            manufacturing_date=line.manufacturing_date,
        )
        return line.model_copy(
            update={
                "batch_id": batch.id,
                "batch_number": None,
                "manufacturing_date": None,
                "expiry_date": None,
            }
        )

    def _line(
        self,
        row: Repack,
        number: int,
        line: RepackLineWrite,
        value: Decimal,
        transaction_id: UUID,
        actor_id: UUID,
    ) -> RepackLine:
        """Keep one posted line."""
        record = RepackLine(
            repack_id=row.id,
            firm_id=row.firm_id,
            line_number=number,
            kind=line.kind,
            product_id=line.product_id,
            batch_id=line.batch_id,
            quantity=line.quantity,
            value=value,
            inventory_transaction_id=transaction_id,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(record)
        return record

    def _audit(self, action: str, row: Repack, actor_id: UUID) -> None:
        """Write one audit row for a repack."""
        record_audit(
            self._session,
            action=action,
            entity_type="repack",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            after_data={
                "repack_number": row.repack_number,
                "consumed_value": str(row.consumed_value),
                "wastage_value": str(row.wastage_value),
                "status": row.status,
            },
        )
