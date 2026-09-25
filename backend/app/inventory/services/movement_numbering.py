"""Number a stock movement from its own series when the user typed none.

Transfers, write-offs, quarantine holds and adjustments made the user type a
reference, 2-80 characters, required -- while every other document took its
number from a series (D-QA-16). References were ad hoc, could repeat, and were
a chore. Each of the four now has a series (``ST``, ``WO``, ``QR``, ``ADJ``); a
typed reference is still taken as it is, for the paper slip's number or an
import that carries its own.
"""

from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

from app.document_framework.services.transactional_document_service import (
    DocumentStateSpec,
    DocumentTypeSpec,
    TransactionalDocumentService,
)
from app.inventory.models import InventoryTransaction

_POSTED = (DocumentStateSpec("POSTED", "Posted", 1, is_terminal=True),)

#: One series per kind of movement, keyed by the kind the service asks for.
MOVEMENT_SERIES: dict[str, DocumentTypeSpec] = {
    kind: DocumentTypeSpec(
        code=code,
        name=name,
        description=f"{name} movement",
        category="INVENTORY",
        module="inventory",
        prefix=prefix,
        states=_POSTED,
    )
    for kind, code, name, prefix in (
        ("TRANSFER", "STOCK_TRANSFER", "Stock Transfer", "ST"),
        ("WRITE_OFF", "STOCK_WRITE_OFF", "Stock Write-off", "WO"),
        ("QUARANTINE", "STOCK_QUARANTINE", "Stock Quarantine", "QR"),
        ("ADJUSTMENT", "STOCK_ADJUSTMENT", "Stock Adjustment", "ADJ"),
    )
}


class MovementNumbering(TransactionalDocumentService):
    """Issue the next number of one movement series, inside the caller's work.

    Reserves under the series row's lock and flushes; it never commits, so a
    movement that is refused afterwards takes its number back with it.
    """

    def __init__(self, session: Session, kind: str) -> None:
        """Bind the series for ``kind`` (a key of ``MOVEMENT_SERIES``)."""
        super().__init__(session)
        self.DOCUMENT = MOVEMENT_SERIES[kind]

    def reference(
        self,
        typed: str | None,
        *,
        firm_id: UUID,
        on: date,
        actor_id: UUID,
    ) -> str:
        """Return the typed reference, normalised, or the series' next number.

        Args:
            typed: What the user entered, if anything.
            firm_id: The owning firm.
            on: The movement's own date, which picks the financial year.
            actor_id: The user making the movement.

        Returns:
            The reference the movement is recorded under.

        """
        if typed is not None and typed.strip():
            return typed.strip().upper()
        _, rule = self._ensure_document_setup(firm_id=firm_id, actor_id=actor_id)
        return self._issue_number(
            rule,
            typed=None,
            number_column=InventoryTransaction.reference_number,
            firm_id=firm_id,
            document_date=on,
            actor_id=actor_id,
            company_code=self._company_code(firm_id),
        )
