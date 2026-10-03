"""Files kept with journals, receipts and payments (ACC-10, decision A88).

The paper behind an entry -- the supplier's bill a payment settles, the bank's
advice for a receipt, the letter behind a write-off journal -- kept beside the
entry rather than in a folder nobody finds a year later. The shape of the
stock evidence (STK-9): a row records where the file is, a reversed or
cancelled entry keeps its files (they explain why it was undone too), and
removing one is audited.
"""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError
from app.core.utils.dates import utc_now
from app.finance.models import JournalEntry
from app.finance.models.ledger_attachment import LedgerAttachment
from app.finance.schemas import LedgerAttachmentWrite
from app.settlements.models import Settlement

#: The settlement directions each route speaks for.
RECEIPT_DIRECTIONS = ("RECEIPT", "REFUND")
PAYMENT_DIRECTIONS = ("PAYMENT",)


class LedgerAttachmentService:
    """Attach, list and remove the files backing ledger entries."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request's firm store."""
        self._session = session

    # ---- journals --------------------------------------------------------

    def for_journal(self, journal_id: UUID, *, firm_id: UUID) -> list[LedgerAttachment]:
        """Return the files kept with one journal entry."""
        self._journal(journal_id, firm_id=firm_id)
        return self._listed(LedgerAttachment.journal_entry_id == journal_id)

    def attach_to_journal(
        self,
        journal_id: UUID,
        files: Sequence[LedgerAttachmentWrite],
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> list[LedgerAttachment]:
        """Keep files with a journal entry; the caller commits."""
        journal = self._journal(journal_id, firm_id=firm_id)
        rows = [
            self._row(file, firm_id=firm_id, actor_id=actor_id, journal_id=journal.id)
            for file in files
        ]
        self._session.flush()
        record_audit(
            self._session,
            action="journal_entry.files_attached",
            entity_type="journal_entry",
            entity_id=journal.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "reference_number": journal.reference_number,
                "files": [row.file_name for row in rows],
            },
        )
        return rows

    # ---- receipts and payments -------------------------------------------

    def for_settlement(
        self, settlement_id: UUID, *, firm_id: UUID, directions: tuple[str, ...]
    ) -> list[LedgerAttachment]:
        """Return the files kept with one receipt, refund or payment."""
        self._settlement(settlement_id, firm_id=firm_id, directions=directions)
        return self._listed(LedgerAttachment.settlement_id == settlement_id)

    def attach_to_settlement(
        self,
        settlement_id: UUID,
        files: Sequence[LedgerAttachmentWrite],
        *,
        firm_id: UUID,
        actor_id: UUID,
        directions: tuple[str, ...],
    ) -> list[LedgerAttachment]:
        """Keep files with a receipt, refund or payment; the caller commits."""
        settlement = self._settlement(
            settlement_id, firm_id=firm_id, directions=directions
        )
        rows = [
            self._row(
                file, firm_id=firm_id, actor_id=actor_id, settlement_id=settlement.id
            )
            for file in files
        ]
        self._session.flush()
        record_audit(
            self._session,
            action="settlement.files_attached",
            entity_type="settlement",
            entity_id=settlement.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "settlement_number": settlement.settlement_number,
                "files": [row.file_name for row in rows],
            },
        )
        return rows

    # ---- removing ----------------------------------------------------------

    def remove(
        self,
        attachment_id: UUID,
        *,
        firm_id: UUID,
        actor_id: UUID,
        journal_id: UUID | None = None,
        settlement_id: UUID | None = None,
    ) -> None:
        """Remove one file reference from the entry it belongs to.

        Raises:
            ResourceNotFoundError: If it is not the firm's, or not that
                entry's -- a route names the entry, so one entry's route
                cannot remove another's file.

        """
        row = self._session.get(LedgerAttachment, attachment_id)
        if (
            row is None
            or row.firm_id != firm_id
            or row.is_deleted
            or (journal_id is not None and row.journal_entry_id != journal_id)
            or (settlement_id is not None and row.settlement_id != settlement_id)
        ):
            raise ResourceNotFoundError("File not found.")
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="ledger_attachment.removed",
            entity_type="ledger_attachment",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={
                "file_name": row.file_name,
                "journal_entry_id": (
                    str(row.journal_entry_id) if row.journal_entry_id else None
                ),
                "settlement_id": str(row.settlement_id) if row.settlement_id else None,
            },
        )

    # ---- helpers -----------------------------------------------------------

    def _journal(self, journal_id: UUID, *, firm_id: UUID) -> JournalEntry:
        """Return the firm's journal entry or refuse it as not found."""
        journal = self._session.get(JournalEntry, journal_id)
        if journal is None or journal.firm_id != firm_id or journal.is_deleted:
            raise ResourceNotFoundError("Journal entry not found.")
        return journal

    def _settlement(
        self, settlement_id: UUID, *, firm_id: UUID, directions: tuple[str, ...]
    ) -> Settlement:
        """Return the firm's settlement of one of ``directions``."""
        row = self._session.get(Settlement, settlement_id)
        if (
            row is None
            or row.firm_id != firm_id
            or row.is_deleted
            or row.direction not in directions
        ):
            raise ResourceNotFoundError("Receipt or payment not found.")
        return row

    def _row(
        self,
        file: LedgerAttachmentWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
        journal_id: UUID | None = None,
        settlement_id: UUID | None = None,
    ) -> LedgerAttachment:
        """Stage one file reference."""
        row = LedgerAttachment(
            firm_id=firm_id,
            journal_entry_id=journal_id,
            settlement_id=settlement_id,
            file_name=file.file_name.strip(),
            mime_type=file.mime_type,
            file_path=file.file_path.strip(),
            caption=(file.caption or "").strip() or None,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        return row

    def _listed(self, *where: object) -> list[LedgerAttachment]:
        """Return the live attachments matching ``where``, oldest first."""
        return list(
            self._session.scalars(
                select(LedgerAttachment)
                .where(LedgerAttachment.is_deleted.is_(False), *where)  # type: ignore[arg-type]
                .order_by(LedgerAttachment.created_at.asc())
            ).all()
        )


__all__ = ["PAYMENT_DIRECTIONS", "RECEIPT_DIRECTIONS", "LedgerAttachmentService"]
