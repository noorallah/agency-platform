"""A firm may require a salesman on every order, delivery note and bill (P2).

``sales_workflow_settings.salesman_required`` is the firm's choice, off unless
it switches it on (``docs/design/SALESMAN_LIST_DESIGN.md``, section 6). The
check runs **after** the server's own fill (`resolve_sales_scope`, or a
document's source), so a save is refused only when nothing could name one.

The setting is read straight off its table rather than through
``SalesWorkflowService``: the three document services call this, and that
service's package imports theirs.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.sales_order.models.sales_order import SalesWorkflowSettings

#: The one refusal, word for word on all three documents.
SALESMAN_REQUIRED_MESSAGE = (
    "This firm requires a salesman on every order, delivery note and bill. "
    "Choose one in the Salesman box."
)


def salesman_required(session: Session, firm_id: UUID) -> bool:
    """Say whether the firm requires a salesman; no settings row means off."""
    return bool(
        session.scalar(
            select(SalesWorkflowSettings.salesman_required).where(
                SalesWorkflowSettings.firm_id == firm_id,
                SalesWorkflowSettings.is_deleted.is_(False),
            )
        )
    )


def assert_salesman_named(
    session: Session, firm_id: UUID, salesman_id: UUID | None
) -> None:
    """Refuse a sales order, delivery note or bill that names no salesman.

    Args:
        session: The firm's own store.
        firm_id: The firm saving the document.
        salesman_id: The salesman the document will hold once saved.

    Raises:
        ValidationError: The firm requires a salesman and none is named.

    """
    if salesman_id is None and salesman_required(session, firm_id):
        raise ValidationError(SALESMAN_REQUIRED_MESSAGE)
