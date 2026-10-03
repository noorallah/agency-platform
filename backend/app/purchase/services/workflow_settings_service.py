"""Decide which buying stages a firm fills in by hand.

The chain is purchase order, goods receipt, supplier bill. A firm run by one
person has the supplier's bill in hand and nothing else, while a firm with a
buyer and a storeman wants the order approved before anything is bought and
the goods counted before they are paid for. Which is which is the firm's
decision, so the policy lives here: one row per firm, the shape
``sales_workflow_settings`` already uses (backlog §38).

Turning a stage off never removes the document. Stock still arrives at the
goods receipt and the accrual still passes through goods received not
invoiced; the difference is only whether a person types the document or the
bill raises it (`PurchaseChainService`).

Approval stays a control wherever a person raises the order: a firm with the
order stage on still submits and approves every order. Only an order the bill
raised is approved by the bill, because the bill's own approval is the
decision there and nobody else would ever see the order.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.branches.models import Branch, Warehouse
from app.common.audit.services import record_audit
from app.core.exceptions import ValidationError
from app.purchase.models import PurchaseWorkflowSettings
from app.purchase.schemas import (
    PurchaseWorkflowSettingsResponse,
    PurchaseWorkflowSettingsWrite,
)

#: What a firm that has never configured anything gets: the whole chain, which
#: is how every firm behaved before this table existed. Never mutated.
DEFAULT_SETTINGS = PurchaseWorkflowSettings(
    purchase_order_stage=True,
    goods_receipt_stage=True,
    default_branch_id=None,
    default_warehouse_id=None,
    bill_price_tolerance_percent=None,
    bill_tolerance_amount=None,
    order_quantity_policy="WARN",
    budget_policy="WARN",
)


class PurchaseWorkflowService:
    """Read and write one firm's buying stage configuration."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session

    def _stored_settings(self, firm_id: UUID) -> PurchaseWorkflowSettings | None:
        """Return the firm's own row, or nothing if it never set one."""
        return self._session.scalar(
            select(PurchaseWorkflowSettings).where(
                PurchaseWorkflowSettings.firm_id == firm_id,
                PurchaseWorkflowSettings.is_deleted.is_(False),
            )
        )

    def settings_for(self, firm_id: UUID) -> PurchaseWorkflowSettings:
        """Return the firm's configuration, or the whole chain by default."""
        stored = self._stored_settings(firm_id)
        return stored if stored is not None else DEFAULT_SETTINGS

    def settings_response(self, firm_id: UUID) -> PurchaseWorkflowSettingsResponse:
        """Report the configuration and whether the firm actually chose it."""
        stored = self._stored_settings(firm_id)
        policy = stored if stored is not None else DEFAULT_SETTINGS
        return self._response(policy, is_configured=stored is not None)

    def update_settings(
        self,
        data: PurchaseWorkflowSettingsWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> PurchaseWorkflowSettingsResponse:
        """Replace the configuration, creating the row on first write.

        Audited on both sides: this decides who confirms that goods arrived,
        and a change nobody can trace is one nobody can explain.
        """
        if data.goods_receipt_stage and not data.purchase_order_stage:
            # A receipt is always raised against an order, so a firm that
            # typed receipts but not orders would have nothing to receive
            # against. Refused here rather than at the first receipt.
            raise ValidationError(
                "A goods receipt is always raised against a purchase order, so "
                "the goods receipt stage cannot be on while the purchase order "
                "stage is off. Switch both off, or keep orders on."
            )
        row = self._stored_settings(firm_id)
        before: dict[str, object] | None = None
        sent = data.model_fields_set
        branch_id = (
            data.default_branch_id
            if "default_branch_id" in sent
            else (row.default_branch_id if row is not None else None)
        )
        warehouse_id = (
            data.default_warehouse_id
            if "default_warehouse_id" in sent
            else (row.default_warehouse_id if row is not None else None)
        )
        if sent & {"default_branch_id", "default_warehouse_id"}:
            self._assert_defaults(firm_id, branch_id, warehouse_id)
        if row is None:
            row = PurchaseWorkflowSettings(firm_id=firm_id, created_by=actor_id)
            self._session.add(row)
        else:
            before = self._snapshot(row)
        row.purchase_order_stage = data.purchase_order_stage
        row.goods_receipt_stage = data.goods_receipt_stage
        row.default_branch_id = branch_id
        row.default_warehouse_id = warehouse_id
        if "bill_price_tolerance_percent" in sent:
            row.bill_price_tolerance_percent = data.bill_price_tolerance_percent
        if "bill_tolerance_amount" in sent:
            row.bill_tolerance_amount = data.bill_tolerance_amount
        if data.budget_policy is not None:
            row.budget_policy = data.budget_policy
        if data.order_quantity_policy is not None:
            row.order_quantity_policy = data.order_quantity_policy
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action=(
                "purchase_workflow_settings.updated"
                if before is not None
                else "purchase_workflow_settings.created"
            ),
            entity_type="purchase_workflow_settings",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data=self._snapshot(row),
        )
        self._session.commit()
        return self._response(row, is_configured=True)

    def _assert_defaults(
        self, firm_id: UUID, branch_id: UUID | None, warehouse_id: UUID | None
    ) -> None:
        """Refuse a default the firm's bills could not receive into.

        The ids have no foreign key a shared store could enforce per firm, so
        an unknown id, another firm's branch, a deleted or inactive one, or a
        warehouse outside the default branch is refused here rather than at
        the first bill.
        """
        branch: Branch | None = None
        if branch_id is not None:
            branch = self._session.scalar(
                select(Branch).where(
                    Branch.id == branch_id,
                    Branch.firm_id == firm_id,
                    Branch.is_deleted.is_(False),
                )
            )
            if branch is None:
                raise ValidationError(
                    "The default branch is not one of this firm's branches."
                )
            if branch.status != "ACTIVE":
                raise ValidationError(
                    f"Branch {branch.code} is {branch.status.lower()}, so goods "
                    "cannot be received into it."
                )
        if warehouse_id is None:
            return
        warehouse = self._session.scalar(
            select(Warehouse).where(
                Warehouse.id == warehouse_id,
                Warehouse.firm_id == firm_id,
                Warehouse.is_deleted.is_(False),
            )
        )
        if warehouse is None:
            raise ValidationError(
                "The default warehouse is not one of this firm's warehouses."
            )
        if warehouse.status != "ACTIVE":
            raise ValidationError(
                f"Warehouse {warehouse.code} is {warehouse.status.lower()}, so "
                "goods cannot be received into it."
            )
        if branch is not None and warehouse.branch_id != branch.id:
            raise ValidationError(
                f"Warehouse {warehouse.code} is not in branch {branch.code}. "
                "The default warehouse must belong to the default branch."
            )

    @staticmethod
    def _response(
        row: PurchaseWorkflowSettings, *, is_configured: bool
    ) -> PurchaseWorkflowSettingsResponse:
        """Build the API view of one configuration."""
        return PurchaseWorkflowSettingsResponse(
            purchase_order_stage=row.purchase_order_stage,
            goods_receipt_stage=row.goods_receipt_stage,
            default_branch_id=row.default_branch_id,
            default_warehouse_id=row.default_warehouse_id,
            bill_price_tolerance_percent=row.bill_price_tolerance_percent,
            bill_tolerance_amount=row.bill_tolerance_amount,
            order_quantity_policy=row.order_quantity_policy or "WARN",
            budget_policy=row.budget_policy or "WARN",
            is_configured=is_configured,
        )

    @staticmethod
    def _snapshot(row: PurchaseWorkflowSettings) -> dict[str, object]:
        """Describe the configuration for the audit trail."""
        return {
            "purchase_order_stage": row.purchase_order_stage,
            "goods_receipt_stage": row.goods_receipt_stage,
            "default_branch_id": (
                str(row.default_branch_id) if row.default_branch_id else None
            ),
            "default_warehouse_id": (
                str(row.default_warehouse_id) if row.default_warehouse_id else None
            ),
            "bill_price_tolerance_percent": (
                None
                if row.bill_price_tolerance_percent is None
                else str(row.bill_price_tolerance_percent)
            ),
            "bill_tolerance_amount": (
                None
                if row.bill_tolerance_amount is None
                else str(row.bill_tolerance_amount)
            ),
            "order_quantity_policy": row.order_quantity_policy,
            "budget_policy": row.budget_policy,
        }
