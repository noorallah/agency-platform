"""Decide which sales stages a firm fills in by hand.

The chain is quotation, sales order, delivery note, invoice. A firm run by one
person has no use for the first three -- four screens for one counter sale --
while a firm with a salesman and a warehouse hand wants all of them. Which is
which is a firm's decision, not the platform's, so the policy lives here: one
row per firm, the shape ``credit_control_settings`` already uses.

Turning a stage off never removes the document. Stock still leaves at dispatch
and cost of goods sold still belongs to the delivery note; the difference is
only whether a person types that document or the service raises it. That is why
this is a workflow setting and not an accounting one.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.sales_order.models import SalesWorkflowSettings
from app.sales_order.schemas import (
    SalesWorkflowSettingsResponse,
    SalesWorkflowSettingsWrite,
)

#: What a firm that has never configured anything gets: the whole chain, which
#: is how every firm behaved before this table existed. Never mutated -- it is
#: the fallback every unconfigured firm shares.
DEFAULT_SETTINGS = SalesWorkflowSettings(
    quotation_stage=True,
    sales_order_stage=True,
    delivery_note_stage=True,
    default_branch_id=None,
    default_warehouse_id=None,
)


class SalesWorkflowService:
    """Read and write one firm's sales stage configuration."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session

    def _stored_settings(self, firm_id: UUID) -> SalesWorkflowSettings | None:
        """Return the firm's own row, or nothing if it never set one."""
        return self._session.scalar(
            select(SalesWorkflowSettings).where(
                SalesWorkflowSettings.firm_id == firm_id,
                SalesWorkflowSettings.is_deleted.is_(False),
            )
        )

    def settings_for(self, firm_id: UUID) -> SalesWorkflowSettings:
        """Return the firm's configuration, or the platform default.

        A firm that has never configured anything keeps the full chain, so
        shipping this cannot change how a single existing firm behaves.
        """
        stored = self._stored_settings(firm_id)
        return stored if stored is not None else DEFAULT_SETTINGS

    def settings_response(self, firm_id: UUID) -> SalesWorkflowSettingsResponse:
        """Report the configuration and whether the firm actually chose it."""
        stored = self._stored_settings(firm_id)
        policy = stored if stored is not None else DEFAULT_SETTINGS
        return SalesWorkflowSettingsResponse(
            quotation_stage=policy.quotation_stage,
            sales_order_stage=policy.sales_order_stage,
            delivery_note_stage=policy.delivery_note_stage,
            default_branch_id=policy.default_branch_id,
            default_warehouse_id=policy.default_warehouse_id,
            is_configured=stored is not None,
        )

    def update_settings(
        self,
        data: SalesWorkflowSettingsWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> SalesWorkflowSettingsResponse:
        """Replace the configuration, creating the row on first write.

        Audited on both sides, because this decides which documents a firm's
        people are asked to raise -- a change nobody can trace is one nobody
        can explain when the screens move.
        """
        row = self._stored_settings(firm_id)
        before: dict[str, object] | None = None
        if row is None:
            row = SalesWorkflowSettings(firm_id=firm_id, created_by=actor_id)
            self._session.add(row)
        else:
            before = self._snapshot(row)
        row.quotation_stage = data.quotation_stage
        row.sales_order_stage = data.sales_order_stage
        row.delivery_note_stage = data.delivery_note_stage
        row.default_branch_id = data.default_branch_id
        row.default_warehouse_id = data.default_warehouse_id
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="UPDATE" if before is not None else "CREATE",
            entity_type="SalesWorkflowSettings",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data=self._snapshot(row),
        )
        self._session.commit()
        return SalesWorkflowSettingsResponse(
            quotation_stage=row.quotation_stage,
            sales_order_stage=row.sales_order_stage,
            delivery_note_stage=row.delivery_note_stage,
            default_branch_id=row.default_branch_id,
            default_warehouse_id=row.default_warehouse_id,
            is_configured=True,
        )

    @staticmethod
    def _snapshot(row: SalesWorkflowSettings) -> dict[str, object]:
        """Describe the configuration for the audit trail."""
        return {
            "quotation_stage": row.quotation_stage,
            "sales_order_stage": row.sales_order_stage,
            "delivery_note_stage": row.delivery_note_stage,
            "default_branch_id": (
                str(row.default_branch_id) if row.default_branch_id else None
            ),
            "default_warehouse_id": (
                str(row.default_warehouse_id) if row.default_warehouse_id else None
            ),
        }
