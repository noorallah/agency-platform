"""The tax rule that decided a line, kept on the line (GST-8, decision A85).

A document line's tax is decided by ``TaxRuleService.simulate``, and until now
only ``tax_rule_execution_logs`` said which rule did it -- a log the retention
service purges after 90 days. A reprint years later, or an auditor asking why
a line was taxed as it was, needs the answer on the line itself.

So each line carries ``tax_rule_code`` and ``tax_rule_version``: the rule's
business code and its ``version_number`` (never ``version``, which is the
concurrency counter). Both are null when no rule matched and the line was
taxed by its profile alone.

Every document module works its lines' tax out in ``_replace_lines``, one
``simulate`` per line keyed by the document and the line number. The tax
service remembers the rule each key matched (``rule_for``), and
``stamps_tax_rules`` copies it onto the document's lines once
``_replace_lines`` returns -- one decorator per module, rather than a return
value threaded through nine different line builders.
"""

from collections.abc import Callable
from functools import wraps
from typing import Any, Protocol, TypeVar, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import InstrumentedAttribute, Session

ResultT = TypeVar("ResultT")


class _RuleSource(Protocol):
    """What a tax service offers to stamp lines with."""

    def rule_for(self, document_id: UUID, line_number: int) -> tuple[str, int] | None:
        """Return the rule code and version that decided one line."""
        ...


def stamp_tax_rules(
    session: Session,
    tax: _RuleSource,
    *,
    line_model: type[Any],
    parent: InstrumentedAttribute[Any],
    document_id: UUID,
) -> None:
    """Copy the matched rule onto every live line of one document."""
    session.flush()
    statement = select(line_model).where(parent == document_id)
    if hasattr(line_model, "is_deleted"):
        statement = statement.where(line_model.is_deleted.is_(False))
    for line in session.scalars(statement).all():
        found = tax.rule_for(document_id, int(line.line_number))
        line.tax_rule_code = None if found is None else found[0]
        line.tax_rule_version = None if found is None else found[1]


def stamps_tax_rules(
    line_model: type[Any], parent_column: str
) -> Callable[[Callable[..., ResultT]], Callable[..., ResultT]]:
    """Stamp a document's lines with their rules after ``_replace_lines``.

    The decorated method takes the document as its first argument after
    ``self``, and its object holds ``_session`` and ``_tax``.
    """

    def decorate(function: Callable[..., ResultT]) -> Callable[..., ResultT]:
        """Wrap one ``_replace_lines``."""

        @wraps(function)
        def run(*args: object, **kwargs: object) -> ResultT:
            """Run the line builder, then stamp what it built."""
            result = function(*args, **kwargs)
            service, document = args[0], args[1]
            stamp_tax_rules(
                cast(Session, getattr(service, "_session")),  # noqa: B009
                cast(_RuleSource, getattr(service, "_tax")),  # noqa: B009
                line_model=line_model,
                parent=getattr(line_model, parent_column),
                document_id=cast(UUID, getattr(document, "id")),  # noqa: B009
            )
            return result

        return run

    return decorate


__all__ = ["stamp_tax_rules", "stamps_tax_rules"]
