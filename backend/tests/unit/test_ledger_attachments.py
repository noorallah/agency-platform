"""Files kept with journals, receipts and payments (ACC-10, decision A88).

A receipt keeps the bank's advice, its journal keeps the covering letter. A
receipt's file is not reachable as a payment's, a file is removed only through
the entry it belongs to, and removing it leaves a line in the trail.
"""

# ruff: noqa: D103

import pytest
from sqlalchemy import select

from app.common.audit.models import AuditLog
from app.core.exceptions import ResourceNotFoundError
from app.finance.schemas import LedgerAttachmentWrite
from app.finance.services.ledger_attachments import (
    PAYMENT_DIRECTIONS,
    RECEIPT_DIRECTIONS,
    LedgerAttachmentService,
)
from tests.unit.test_settlements import _Books, _receipt, _session_factory

ADVICE = LedgerAttachmentWrite(
    file_name="advice.pdf",
    mime_type="application/pdf",
    file_path="\\\\server\\scans\\advice.pdf",
    caption=" bank advice ",
)


def test_a_receipt_and_its_journal_keep_their_own_files() -> None:
    books = _Books(_session_factory()())
    books.owe_us("1000")
    receipt = _receipt(books, "1000")
    books.session.commit()
    files = LedgerAttachmentService(books.session)

    [kept] = files.attach_to_settlement(
        receipt.id,
        [ADVICE],
        firm_id=books.firm.id,
        actor_id=books.actor_id,
        directions=RECEIPT_DIRECTIONS,
    )
    books.session.commit()
    assert kept.caption == "bank advice"
    assert [
        row.file_name
        for row in files.for_settlement(
            receipt.id, firm_id=books.firm.id, directions=RECEIPT_DIRECTIONS
        )
    ] == ["advice.pdf"]
    with pytest.raises(ResourceNotFoundError):
        files.for_settlement(
            receipt.id, firm_id=books.firm.id, directions=PAYMENT_DIRECTIONS
        )

    assert receipt.journal_entry_id is not None
    files.attach_to_journal(
        receipt.journal_entry_id,
        [ADVICE.model_copy(update={"file_name": "letter.pdf"})],
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    assert [
        row.file_name
        for row in files.for_journal(receipt.journal_entry_id, firm_id=books.firm.id)
    ] == ["letter.pdf"], "the journal's files are its own"

    with pytest.raises(ResourceNotFoundError):
        files.remove(
            kept.id,
            firm_id=books.firm.id,
            actor_id=books.actor_id,
            journal_id=receipt.journal_entry_id,
        )
    files.remove(
        kept.id,
        firm_id=books.firm.id,
        actor_id=books.actor_id,
        settlement_id=receipt.id,
    )
    books.session.commit()
    assert not files.for_settlement(
        receipt.id, firm_id=books.firm.id, directions=RECEIPT_DIRECTIONS
    )
    assert books.session.scalar(
        select(AuditLog.id).where(AuditLog.action == "ledger_attachment.removed")
    ), "removing a file is in the trail"
