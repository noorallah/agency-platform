"""Act on many documents, each through the service a single action uses.

Backlog 56 A; `docs/BULK_APPROVAL_MIGRATION_AND_YEAR_DATA.md` section 2.

**Per row, not all-or-nothing.** One order over its credit limit must not
hold back eleven good ones, so each row is acted on and committed on its own
by the very method the single endpoint calls -- the credit check, the stock
reservation, the promotion claim, the posting and the audit row all run. A
row the service refuses is rolled back and reported with the service's own
message, and the next row goes ahead. That is the opposite of an import,
which is all-or-nothing because a half-loaded file is worse than none.
"""

from collections.abc import Callable, Sequence
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.core.exceptions import ApplicationError
from app.document_framework.schemas.bulk_actions import (
    BulkActionResult,
    BulkRow,
    BulkRowResult,
)

#: Said of a row whose version moved after the list was read.
CHANGED_SINCE_READ = (
    "was changed after the list was read; open it, check it and try again."
)


def run_each(
    session: Session,
    items: Sequence[BulkRow],
    *,
    load: Callable[[UUID], Any],
    act: Callable[[UUID], Any],
    number: Callable[[Any], str],
) -> BulkActionResult:
    """Run ``act`` on every row, each in its own transaction.

    Args:
        session: The request's session; rolled back after a refused row so
            the next one starts clean.
        items: The ticked rows, in the order to report them. A row named
            twice is acted on once.
        load: Read one document, raising if it is not the firm's.
        act: The single action -- approve, cancel -- which commits.
        number: The document's number, to say which one a result is about.

    Returns:
        Each row done or refused, with the service's reason for a refusal.

    """
    results: list[BulkRowResult] = []
    seen: set[UUID] = set()
    for item in items:
        if item.id in seen:
            continue
        seen.add(item.id)
        label: str | None = None
        try:
            row = load(item.id)
            label = number(row)
            if item.version is not None and row.version != item.version:
                results.append(
                    BulkRowResult(
                        id=item.id,
                        number=label,
                        outcome="REFUSED",
                        message=f"{label} {CHANGED_SINCE_READ}",
                    )
                )
                continue
            act(item.id)
        except ApplicationError as error:
            session.rollback()
            results.append(
                BulkRowResult(
                    id=item.id, number=label, outcome="REFUSED", message=error.message
                )
            )
            continue
        except StaleDataError:
            session.rollback()
            results.append(
                BulkRowResult(
                    id=item.id,
                    number=label,
                    outcome="REFUSED",
                    message=f"{label or 'The document'} {CHANGED_SINCE_READ}",
                )
            )
            continue
        results.append(BulkRowResult(id=item.id, number=label, outcome="DONE"))
    done = sum(1 for result in results if result.outcome == "DONE")
    return BulkActionResult(done=done, refused=len(results) - done, results=results)


__all__ = ["CHANGED_SINCE_READ", "run_each"]
