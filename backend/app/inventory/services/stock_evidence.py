"""Photos and documents kept with stock movements and count sheets (STK-9).

Every write-off, adjustment, transfer and count is a decision somebody may
later be asked to justify -- by an auditor, an insurer, a supplier disputing a
damage claim. The photo of the crushed cartons or the signed transfer slip is
the justification, and it belongs beside the movement rather than in a shared
folder nobody can find a year later.

A transfer is two movements, one out and one in. Its evidence is kept on the
outbound leg and read from either, so whichever line somebody opens in the
movement list shows the same files.
"""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import ColumnElement, select
from sqlalchemy.orm import Session

from app.business.gating import assert_feature_fields
from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.inventory.models import InventoryTransaction, PhysicalCount, StockAttachment
from app.inventory.schemas import (
    MAX_STOCK_ATTACHMENTS,
    InventoryTransactionType,
    StockAttachmentResponse,
    StockAttachmentWrite,
)


class StockEvidenceService:
    """Attach, list and remove the files backing stock decisions."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request's firm store."""
        self._session = session

    def stage_for_movement(
        self,
        movement: InventoryTransaction,
        files: Sequence[StockAttachmentWrite],
        *,
        actor_id: UUID,
    ) -> list[StockAttachment]:
        """Keep files with a movement, flushed but not committed.

        Args:
            movement: The movement the files back; a transfer's inbound leg
                hands them to its outbound one.
            files: What to keep. Empty writes nothing.
            actor_id: Who attached them.

        Returns:
            The rows written.

        """
        if not files:
            return []
        holder = self._outbound_leg(movement)
        rows = self._stage(
            files,
            firm_id=movement.firm_id,
            actor_id=actor_id,
            movement_id=holder.id,
        )
        record_audit(
            self._session,
            action="inventory.evidence_attached",
            entity_type="inventory_transaction",
            entity_id=holder.id,
            actor_id=actor_id,
            firm_id=movement.firm_id,
            after_data={
                "reference_number": holder.reference_number,
                "files": [row.file_name for row in rows],
            },
        )
        return rows

    def attach_to_movement(
        self,
        movement_id: UUID,
        files: Sequence[StockAttachmentWrite],
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> list[StockAttachment]:
        """Keep files with a movement already posted, and commit."""
        movement = self._movement(movement_id, firm_id=firm_id)
        rows = self.stage_for_movement(movement, files, actor_id=actor_id)
        self._session.commit()
        return rows

    def attach_to_count(
        self,
        count_id: UUID,
        files: Sequence[StockAttachmentWrite],
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> list[StockAttachment]:
        """Keep files with a count sheet, in any state, and commit.

        A posted sheet still takes evidence: the photo of the empty shelf is
        often found after the variance is.
        """
        count = self._count(count_id, firm_id=firm_id)
        rows = self._stage(files, firm_id=firm_id, actor_id=actor_id, count_id=count.id)
        record_audit(
            self._session,
            action="inventory.evidence_attached",
            entity_type="physical_count",
            entity_id=count.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "count_number": count.count_number,
                "files": [row.file_name for row in rows],
            },
        )
        self._session.commit()
        return rows

    def for_movement(
        self, movement_id: UUID, *, firm_id: UUID
    ) -> list[StockAttachment]:
        """Return the files backing a movement, oldest first."""
        holder = self._outbound_leg(self._movement(movement_id, firm_id=firm_id))
        return self._listed(StockAttachment.inventory_transaction_id == holder.id)

    def for_count(self, count_id: UUID, *, firm_id: UUID) -> list[StockAttachment]:
        """Return the files kept with a count sheet, oldest first."""
        count = self._count(count_id, firm_id=firm_id)
        return self._listed(StockAttachment.physical_count_id == count.id)

    def remove(self, attachment_id: UUID, *, firm_id: UUID, actor_id: UUID) -> None:
        """Take a file off its movement or sheet; the trail keeps that it was."""
        row = self._session.scalar(
            select(StockAttachment).where(
                StockAttachment.id == attachment_id,
                StockAttachment.firm_id == firm_id,
                StockAttachment.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Attachment not found.")
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id
        on_count = row.physical_count_id is not None
        record_audit(
            self._session,
            action="inventory.evidence_removed",
            entity_type="physical_count" if on_count else "inventory_transaction",
            entity_id=row.physical_count_id or row.inventory_transaction_id or row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={"file_name": row.file_name, "file_path": row.file_path},
        )
        self._session.commit()

    @staticmethod
    def response(row: StockAttachment) -> StockAttachmentResponse:
        """Expose one attachment."""
        return StockAttachmentResponse.model_validate(row)

    def _stage(
        self,
        files: Sequence[StockAttachmentWrite],
        *,
        firm_id: UUID,
        actor_id: UUID,
        movement_id: UUID | None = None,
        count_id: UUID | None = None,
    ) -> list[StockAttachment]:
        """Write the rows under one parent, refused where the firm has no files."""
        assert_feature_fields(
            self._session,
            firm_id,
            feature="ATTACHMENTS",
            values={"attachments": list(files)},
        )
        parent = (
            StockAttachment.physical_count_id == count_id
            if count_id is not None
            else StockAttachment.inventory_transaction_id == movement_id
        )
        held = len(self._listed(parent))
        if held + len(files) > MAX_STOCK_ATTACHMENTS:
            # The cap on one request is the cap on what the record keeps, or
            # it is no cap: ten at a time, any number of times (D-STK-62).
            what = "A count sheet" if count_id is not None else "A stock movement"
            raise ValidationError(
                f"{what} keeps at most {MAX_STOCK_ATTACHMENTS} files and this "
                f"one holds {held}, so {len(files)} more cannot be added. "
                "Remove one first."
            )
        rows = [
            StockAttachment(
                firm_id=firm_id,
                inventory_transaction_id=movement_id,
                physical_count_id=count_id,
                file_name=item.file_name.strip(),
                mime_type=item.mime_type,
                file_path=item.file_path.strip(),
                caption=(item.caption or "").strip() or None,
                created_by=actor_id,
                updated_by=actor_id,
            )
            for item in files
        ]
        self._session.add_all(rows)
        self._session.flush()
        return rows

    def _listed(self, parent: ColumnElement[bool]) -> list[StockAttachment]:
        """Return the live rows under one parent, oldest first."""
        return list(
            self._session.scalars(
                select(StockAttachment)
                .where(parent, StockAttachment.is_deleted.is_(False))
                .order_by(StockAttachment.created_at, StockAttachment.file_name)
            )
        )

    def _movement(self, movement_id: UUID, *, firm_id: UUID) -> InventoryTransaction:
        """Return the firm's movement, or refuse by name."""
        movement = self._session.scalar(
            select(InventoryTransaction).where(
                InventoryTransaction.id == movement_id,
                InventoryTransaction.firm_id == firm_id,
                InventoryTransaction.is_deleted.is_(False),
            )
        )
        if movement is None:
            raise ResourceNotFoundError("Stock movement not found.")
        return movement

    def _count(self, count_id: UUID, *, firm_id: UUID) -> PhysicalCount:
        """Return the firm's count sheet, or refuse by name."""
        count = self._session.scalar(
            select(PhysicalCount).where(
                PhysicalCount.id == count_id,
                PhysicalCount.firm_id == firm_id,
                PhysicalCount.is_deleted.is_(False),
            )
        )
        if count is None:
            raise ResourceNotFoundError("Physical count not found.")
        return count

    def _outbound_leg(self, movement: InventoryTransaction) -> InventoryTransaction:
        """Return the movement that holds evidence for ``movement``.

        Itself, unless it is a transfer's inbound leg: then the outbound leg
        written beside it -- same number, product, batch, day and quantity.
        """
        if movement.transaction_type != InventoryTransactionType.TRANSFER_IN.value:
            return movement
        batch = (
            InventoryTransaction.batch_id.is_(None)
            if movement.batch_id is None
            else InventoryTransaction.batch_id == movement.batch_id
        )
        outbound = self._session.scalar(
            select(InventoryTransaction)
            .where(
                InventoryTransaction.firm_id == movement.firm_id,
                InventoryTransaction.transaction_type
                == InventoryTransactionType.TRANSFER_OUT.value,
                InventoryTransaction.reference_number == movement.reference_number,
                InventoryTransaction.product_id == movement.product_id,
                batch,
                InventoryTransaction.transaction_date == movement.transaction_date,
                InventoryTransaction.quantity == movement.quantity,
                InventoryTransaction.is_deleted.is_(False),
            )
            .order_by(
                InventoryTransaction.created_at.desc(), InventoryTransaction.id.desc()
            )
            .limit(1)
        )
        return outbound or movement
