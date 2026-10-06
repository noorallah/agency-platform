"""A draft delivery note shows what its order line has left now.

D-PRC-43, from the third pricing check: drafts of 6 and 4 of an order line
of 10. The draft of 4 read ``remaining_quantity`` 6 and
``previously_delivered_quantity`` 0 when it was saved, and went on reading
them after the draft of 6 was approved and after it was dispatched, on the
note and on the list -- where nothing was left. The cap behind it was right
(a third draft of 5 was refused); only the figure shown was stale.

The two figures (and the short shipment and the note's total, which follow
them) are **derived when a draft is read**. An approved note shows what was
true when it was approved, written at approval, because that is what its
challan states.

Every case runs on a request-shaped session (autoflush off).
"""

from decimal import Decimal

import pytest

from app.core.exceptions import ValidationError
from app.delivery_note.models import DeliveryNote
from app.delivery_note.schemas import DeliveryNoteLineResponse, DeliveryNoteResponse
from app.sales_order.models import SalesOrder
from tests.unit.test_order_bill_discount_reaches_the_bill import _Trade

D = Decimal


class _Drafts(_Trade):
    """The check's order: 10 of the product, delivered by notes of 6 and 4."""

    def __init__(self) -> None:
        """Approve the order and save both notes as drafts."""
        super().__init__()
        self.sale: SalesOrder = self.order("10")
        self.six: DeliveryNote = self.note(self.sale, "6", ship=False)
        self.four: DeliveryNote = self.note(self.sale, "4", ship=False)

    def read(self, note: DeliveryNote) -> DeliveryNoteResponse:
        """Read one note as `GET /delivery-notes/{id}` answers it."""
        self.session.expire_all()
        return self.notes.note_response(
            self.notes.get_note(note.id, firm_scope=self.firm_id)
        )

    def line(self, note: DeliveryNote) -> DeliveryNoteLineResponse:
        """Return the note's one line as the API answers it."""
        return self.read(note).lines[0]

    def figures(self, note: DeliveryNote) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        """Return (delivered before, remaining, short, the note's total before)."""
        answer = self.read(note)
        line = answer.lines[0]
        return (
            line.previously_delivered_quantity,
            line.remaining_quantity,
            line.short_shipment_quantity,
            answer.total_previously_delivered_quantity,
        )

    def approve(self, note: DeliveryNote) -> None:
        """Approve a note."""
        self.notes.approve_note(note.id, firm_scope=self.firm_id, actor_id=self.actor)

    def dispatch(self, note: DeliveryNote) -> None:
        """Dispatch a note."""
        self.notes.dispatch_note(note.id, firm_scope=self.firm_id, actor_id=self.actor)


def test_a_draft_reads_what_is_left_after_another_note_is_approved() -> None:
    """The check's steps: 6 remaining, then nothing, on the note itself."""
    drafts = _Drafts()
    assert drafts.figures(drafts.four) == (D("0"), D("6.0000"), D("6.0000"), D("0"))

    drafts.approve(drafts.six)

    assert drafts.figures(drafts.four) == (
        D("6.0000"),
        D("0.0000"),
        D("0.0000"),
        D("6.0000"),
    )
    drafts.dispatch(drafts.six)
    assert drafts.figures(drafts.four) == (
        D("6.0000"),
        D("0.0000"),
        D("0.0000"),
        D("6.0000"),
    )
    # The cap behind the figure was always right.
    with pytest.raises(ValidationError, match="exceeds allowed quantity"):
        drafts.note(drafts.sale, "5", ship=False)


def test_the_list_reads_the_same_figures_as_the_note() -> None:
    """A page of notes derives every draft's figures, each equal to its own read."""
    drafts = _Drafts()
    drafts.approve(drafts.six)
    drafts.session.expire_all()

    page = drafts.notes.note_responses(
        [
            drafts.notes.get_note(note.id, firm_scope=drafts.firm_id)
            for note in (drafts.six, drafts.four)
        ]
    )

    listed = {
        row.id: (
            row.lines[0].previously_delivered_quantity,
            row.lines[0].remaining_quantity,
        )
        for row in page
    }
    assert listed == {
        drafts.six.id: (D("0.0000"), D("4.0000")),
        drafts.four.id: (D("6.0000"), D("0.0000")),
    }
    assert page[1] == drafts.read(drafts.four)


def test_an_approved_note_keeps_what_was_true_when_it_was_approved() -> None:
    """The 6 was approved first: 4 were left then, and it goes on saying so."""
    drafts = _Drafts()
    drafts.approve(drafts.six)
    drafts.approve(drafts.four)
    drafts.dispatch(drafts.six)
    drafts.dispatch(drafts.four)

    assert drafts.figures(drafts.six) == (D("0"), D("4.0000"), D("4.0000"), D("0"))
    assert drafts.figures(drafts.four) == (
        D("6.0000"),
        D("0.0000"),
        D("0.0000"),
        D("6.0000"),
    )


def test_approval_writes_what_the_draft_was_showing() -> None:
    """Saved seeing nothing delivered; approved after 6 were: the row says 6."""
    drafts = _Drafts()
    drafts.approve(drafts.six)
    stored = drafts.note_line(drafts.four)
    assert (stored.previously_delivered_quantity, stored.remaining_quantity) == (
        D("0.0000"),
        D("6.0000"),
    ), "the draft's own row is still as it was saved"

    drafts.approve(drafts.four)

    drafts.session.expire_all()
    stored = drafts.note_line(drafts.four)
    assert (
        stored.previously_delivered_quantity,
        stored.remaining_quantity,
        stored.short_shipment_quantity,
    ) == (D("6.0000"), D("0.0000"), D("0.0000"))
    note = drafts.notes.get_note(drafts.four.id, firm_scope=drafts.firm_id)
    assert note.total_previously_delivered_quantity == D("6.0000")


def test_a_cancelled_note_gives_the_draft_its_quantity_back() -> None:
    """The approved 6 is cancelled: the draft of 4 reads 6 remaining again."""
    drafts = _Drafts()
    drafts.approve(drafts.six)
    assert drafts.line(drafts.four).remaining_quantity == D("0.0000")

    drafts.notes.cancel_note(
        drafts.six.id, firm_scope=drafts.firm_id, actor_id=drafts.actor, reason="Wrong"
    )

    assert drafts.figures(drafts.four) == (D("0"), D("6.0000"), D("6.0000"), D("0"))
