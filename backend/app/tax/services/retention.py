"""Retention for the tax execution log, which would otherwise grow without bound.

``tax_rule_execution_logs`` is the fastest-growing table in the system and
nothing ever removed a row: every transactional module calls
``TaxRuleService.simulate`` once per document line, and each call stores three
JSON documents (the request, the full evaluation trace, and the result).

The rule is a retention window, like ``login_history``: the log is evidence of
which rule decided a rate, so it is kept for a period and then pruned. Rows are
deleted per firm, because a firm's log lives in that firm's own store.
"""

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.utils.dates import utc_now
from app.tax.models import TaxRuleExecutionLog


@dataclass(frozen=True, slots=True)
class TaxRetentionResult:
    """Report how many execution log rows the rule removed."""

    execution_logs: int


class TaxRetentionService:
    """Prune tax execution logs beyond the retention window."""

    def __init__(self, session: Session) -> None:
        """Bind the service to one unit of work."""
        self._session = session

    def purge(
        self,
        *,
        execution_log_days: int = 365,
        firm_scope: UUID | None = None,
        dry_run: bool = False,
    ) -> TaxRetentionResult:
        """Remove execution logs older than the retention window.

        Args:
            execution_log_days: Retention window in days. Must be at least one,
                so a mistyped zero cannot erase the log the moment it is written.
            firm_scope: Limit the purge to one firm. ``None`` prunes every firm
                in the store this session is bound to.
            dry_run: Report what would be removed without deleting anything.

        Returns:
            The number of rows removed, or that would be removed.

        Raises:
            ValueError: If the retention window is shorter than a day.

        """
        if execution_log_days < 1:
            raise ValueError("execution_log_days must be at least 1.")
        cutoff = utc_now() - timedelta(days=execution_log_days)
        statement = select(TaxRuleExecutionLog.id).where(
            TaxRuleExecutionLog.created_at < cutoff
        )
        if firm_scope is not None:
            statement = statement.where(TaxRuleExecutionLog.firm_id == firm_scope)
        stale = list(self._session.scalars(statement).all())
        result = TaxRetentionResult(execution_logs=len(stale))
        if dry_run or not stale:
            return result
        self._session.execute(
            delete(TaxRuleExecutionLog).where(TaxRuleExecutionLog.id.in_(stale))
        )
        self._session.commit()
        return result
