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

from app.branches.models import Branch, Warehouse
from app.common.audit.services import record_audit
from app.core.exceptions import ValidationError
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
    promotion_mode="COMBINE",
    max_line_discount_percent=None,
    rate_includes_tax=False,
    new_outlets_need_approval=False,
    reservation_lapse_days=None,
    sales_order_approval=True,
    delivery_note_approval=True,
    sales_invoice_approval=True,
    round_bills_to_rupee=False,
    salesman_required=False,
    box_and_piece_entry=False,
)

#: The approval switch of each document that has one (backlog 119).
APPROVAL_SWITCHES = (
    "sales_order_approval",
    "delivery_note_approval",
    "sales_invoice_approval",
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

    def approval_is_a_step(self, firm_id: UUID, switch: str) -> bool:
        """Say whether a new document of this kind waits for an approver.

        ``switch`` is one of ``APPROVAL_SWITCHES``. The answer is stamped
        on the document as it is raised, so a later change to the setting
        never reaches a document already made (backlog 119).
        """
        return bool(getattr(self.settings_for(firm_id), switch))

    def rounds_bills(self, firm_id: UUID) -> bool:
        """Say whether the firm rounds every bill to the nearest rupee.

        Asked when a sales bill or a credit note is saved, where the server
        then works the round-off out itself, and when one posts, where the
        round-off goes to the Rounding account (backlog 134).
        """
        return bool(self.settings_for(firm_id).round_bills_to_rupee)

    def requires_salesman(self, firm_id: UUID) -> bool:
        """Say whether the firm requires a salesman on its sales documents.

        No row means off (P2, salesman list design section 6).
        """
        return bool(self.settings_for(firm_id).salesman_required)

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
            promotion_mode=policy.promotion_mode or "COMBINE",
            max_line_discount_percent=policy.max_line_discount_percent,
            rate_includes_tax=bool(policy.rate_includes_tax),
            new_outlets_need_approval=bool(policy.new_outlets_need_approval),
            reservation_lapse_days=policy.reservation_lapse_days,
            sales_order_approval=bool(policy.sales_order_approval),
            delivery_note_approval=bool(policy.delivery_note_approval),
            sales_invoice_approval=bool(policy.sales_invoice_approval),
            round_bills_to_rupee=bool(policy.round_bills_to_rupee),
            salesman_required=bool(policy.salesman_required),
            box_and_piece_entry=bool(policy.box_and_piece_entry),
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
        # A delivery note continues a sales order: its lines are the order's
        # lines, and nothing raises the order behind a note typed without
        # one. With the order switched off and the note on, neither a bill
        # nor a note could be typed at all (D-SELL-103).
        if data.delivery_note_stage and not data.sales_order_stage:
            raise ValidationError(
                "A delivery note is raised from a sales order, so the "
                "Delivery note stage cannot be on while the Sales order stage "
                "is off. Switch Sales order on, or switch Delivery note off "
                "and the bill raises the note itself.",
                details={"field": "delivery_note_stage"},
            )
        row = self._stored_settings(firm_id)
        before: dict[str, object] | None = None
        # The stages are required on every write; the two defaults are not.
        # An omitted default is left alone and an explicit null clears it --
        # a client that never showed them must not wipe them (D-CFG-14).
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
            # Off until chosen: a row not yet flushed has no column default.
            row = SalesWorkflowSettings(
                firm_id=firm_id,
                created_by=actor_id,
                round_bills_to_rupee=False,
                salesman_required=False,
                box_and_piece_entry=False,
            )
            self._session.add(row)
        else:
            before = self._snapshot(row)
        row.quotation_stage = data.quotation_stage
        row.sales_order_stage = data.sales_order_stage
        row.delivery_note_stage = data.delivery_note_stage
        row.default_branch_id = branch_id
        row.default_warehouse_id = warehouse_id
        if data.promotion_mode is not None:
            row.promotion_mode = data.promotion_mode
        elif not row.promotion_mode:
            row.promotion_mode = "COMBINE"
        if "max_line_discount_percent" in sent:
            row.max_line_discount_percent = data.max_line_discount_percent
        # Omitted is left as it is: an editor that never showed it must not
        # switch it off.
        if data.rate_includes_tax is not None:
            row.rate_includes_tax = data.rate_includes_tax
        if data.new_outlets_need_approval is not None:
            row.new_outlets_need_approval = data.new_outlets_need_approval
        if "reservation_lapse_days" in sent:
            row.reservation_lapse_days = data.reservation_lapse_days
        for switch in APPROVAL_SWITCHES:
            chosen = getattr(data, switch)
            if chosen is not None:
                setattr(row, switch, chosen)
            elif getattr(row, switch) is None:
                # A row not yet flushed has no column default to read.
                setattr(row, switch, True)
        if data.round_bills_to_rupee is not None:
            row.round_bills_to_rupee = data.round_bills_to_rupee
        if data.salesman_required is not None:
            row.salesman_required = data.salesman_required
        if data.box_and_piece_entry is not None:
            row.box_and_piece_entry = data.box_and_piece_entry
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action=(
                "sales_workflow_settings.updated"
                if before is not None
                else "sales_workflow_settings.created"
            ),
            entity_type="sales_workflow_settings",
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
            promotion_mode=row.promotion_mode,
            max_line_discount_percent=row.max_line_discount_percent,
            rate_includes_tax=row.rate_includes_tax,
            new_outlets_need_approval=row.new_outlets_need_approval,
            reservation_lapse_days=row.reservation_lapse_days,
            sales_order_approval=row.sales_order_approval,
            delivery_note_approval=row.delivery_note_approval,
            sales_invoice_approval=row.sales_invoice_approval,
            round_bills_to_rupee=row.round_bills_to_rupee,
            salesman_required=row.salesman_required,
            box_and_piece_entry=row.box_and_piece_entry,
            is_configured=True,
        )

    def _assert_defaults(
        self, firm_id: UUID, branch_id: UUID | None, warehouse_id: UUID | None
    ) -> None:
        """Refuse a default the firm's bills could not ship from.

        The ids have no foreign key -- the row lives beside ``branches`` in a
        store other firms may share -- so an unknown id, another firm's
        branch, a deleted or inactive one, or a warehouse outside the default
        branch was saved and failed only at bill time (D-CFG-14).
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
                    f"Branch {branch.code} is {branch.status.lower()}, so bills "
                    "cannot ship from it."
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
                "bills cannot ship from it."
            )
        if branch is not None and warehouse.branch_id != branch.id:
            raise ValidationError(
                f"Warehouse {warehouse.code} is not in branch {branch.code}. "
                "The default warehouse must belong to the default branch."
            )

    @staticmethod
    def _snapshot(row: SalesWorkflowSettings) -> dict[str, object]:
        """Describe the configuration for the audit trail."""
        return {
            "promotion_mode": row.promotion_mode,
            "max_line_discount_percent": (
                str(row.max_line_discount_percent)
                if row.max_line_discount_percent is not None
                else None
            ),
            "rate_includes_tax": row.rate_includes_tax,
            "new_outlets_need_approval": row.new_outlets_need_approval,
            "reservation_lapse_days": row.reservation_lapse_days,
            **{switch: getattr(row, switch) for switch in APPROVAL_SWITCHES},
            "round_bills_to_rupee": row.round_bills_to_rupee,
            "salesman_required": row.salesman_required,
            "box_and_piece_entry": row.box_and_piece_entry,
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
