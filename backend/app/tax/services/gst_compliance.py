"""A firm's GST document policy, and judging a dispatch against it.

Backlog 77 rows 1-2, decision A35. A tax invoice for goods is issued at or
before their removal (CGST Act s.31(1)); goods may leave first only on a
delivery challan with a reason the rules allow (CGST Rules r.55): on approval,
job work, quantity not known at removal. The sales chain let a sale's delivery
note be dispatched with no invoice and no reason, and invoiced in the evening.

Every delivery note now says why it goes out, and dispatching a **sale** by
hand -- before an invoice exists -- is judged by the firm's policy: OFF says
nothing, WARN (the default) lets it go and records the warning on the dispatch,
BLOCK refuses it and points at *Dispatch and invoice*, which raises the invoice
in the same transaction. A bill that dispatches the note it raised for itself
is the invoice existing at removal, so it is never judged.

A van or route sale is a sale whose quantities are settled at each shop. Some
CAs accept it on a challan and some want the invoices first, so the firm says
which (``route_sale_needs_invoice``).
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ValidationError
from app.tax.models import GstComplianceSettings
from app.tax.schemas.gst_compliance import (
    DispatchCheckResponse,
    GstComplianceSettingsResponse,
    GstComplianceSettingsWrite,
)

#: The policy every firm without a row shares.
DEFAULT_DISPATCH_WITHOUT_INVOICE = "WARN"
#: The national e-way bill limit; a firm sets its own state's (A35).
DEFAULT_EWAY_BILL_LIMIT = Decimal("50000")

#: Why a delivery note goes out. SALE is the default; the rest are the
#: movements a challan may carry ahead of the invoice.
CHALLAN_REASONS: dict[str, str] = {
    "SALE": "Sale",
    "ROUTE_SALE": "Van or route sale",
    "ON_APPROVAL": "Supply on approval",
    "QUANTITY_UNKNOWN": "Quantity not known at removal",
    "JOB_WORK": "Job work",
    "OTHER": "Other",
}


class GstComplianceService:
    """The firm's GST document policy."""

    def __init__(self, session: Session) -> None:
        """Hold the session the firm's documents are written on."""
        self._session = session

    def _stored(self, firm_id: UUID) -> GstComplianceSettings | None:
        """Return the firm's own row, or None if it never chose."""
        return self._session.scalar(
            select(GstComplianceSettings).where(
                GstComplianceSettings.firm_id == firm_id,
                GstComplianceSettings.is_deleted.is_(False),
            )
        )

    def settings_response(self, firm_id: UUID) -> GstComplianceSettingsResponse:
        """Report the firm's policy and whether the firm actually chose it."""
        stored = self._stored(firm_id)
        if stored is None:
            return GstComplianceSettingsResponse(
                einvoice_applicable_from=None,
                thirty_day_rule_from=None,
                dispatch_without_invoice=DEFAULT_DISPATCH_WITHOUT_INVOICE,
                route_sale_needs_invoice=False,
                itc_claim_basis="ALL",
                gstr2b_tolerance=Decimal("1.00"),
                eway_bill_limit=DEFAULT_EWAY_BILL_LIMIT,
                is_configured=False,
            )
        return GstComplianceSettingsResponse(
            einvoice_applicable_from=stored.einvoice_applicable_from,
            thirty_day_rule_from=stored.thirty_day_rule_from,
            dispatch_without_invoice=stored.dispatch_without_invoice,
            route_sale_needs_invoice=stored.route_sale_needs_invoice,
            itc_claim_basis=stored.itc_claim_basis or "ALL",
            gstr2b_tolerance=Decimal(str(stored.gstr2b_tolerance)),
            eway_bill_limit=Decimal(str(stored.eway_bill_limit)),
            is_configured=True,
        )

    def update_settings(
        self, data: GstComplianceSettingsWrite, *, firm_id: UUID, actor_id: UUID
    ) -> GstComplianceSettingsResponse:
        """Replace the firm's policy, creating its row on the first write."""
        row = self._stored(firm_id)
        before: dict[str, object] | None = None
        if row is None:
            row = GstComplianceSettings(firm_id=firm_id, created_by=actor_id)
            self._session.add(row)
        else:
            before = self._state(row)
        row.einvoice_applicable_from = data.einvoice_applicable_from
        row.thirty_day_rule_from = data.thirty_day_rule_from
        row.dispatch_without_invoice = data.dispatch_without_invoice
        row.route_sale_needs_invoice = data.route_sale_needs_invoice
        if data.itc_claim_basis is not None:
            row.itc_claim_basis = data.itc_claim_basis
        if data.gstr2b_tolerance is not None:
            row.gstr2b_tolerance = data.gstr2b_tolerance
        if data.eway_bill_limit is not None:
            row.eway_bill_limit = data.eway_bill_limit
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action=(
                "gst_compliance_settings.updated"
                if before is not None
                else "gst_compliance_settings.created"
            ),
            entity_type="gst_compliance_settings",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data=self._state(row),
        )
        self._session.commit()
        return self.settings_response(firm_id)

    @staticmethod
    def _state(row: GstComplianceSettings) -> dict[str, object]:
        """Return the row as the audit trail keeps it."""
        return {
            "einvoice_applicable_from": (
                row.einvoice_applicable_from.isoformat()
                if row.einvoice_applicable_from
                else None
            ),
            "thirty_day_rule_from": (
                row.thirty_day_rule_from.isoformat()
                if row.thirty_day_rule_from
                else None
            ),
            "dispatch_without_invoice": row.dispatch_without_invoice,
            "route_sale_needs_invoice": row.route_sale_needs_invoice,
            "eway_bill_limit": str(row.eway_bill_limit),
            "itc_claim_basis": row.itc_claim_basis,
            "gstr2b_tolerance": str(row.gstr2b_tolerance),
        }

    def dispatch_check(
        self, firm_id: UUID, *, note_number: str, challan_reason: str
    ) -> DispatchCheckResponse:
        """Say what dispatching this note by hand, with no invoice, would meet."""
        policy = self.settings_response(firm_id)
        reason = challan_reason or "SALE"
        judged = reason == "SALE" or (
            reason == "ROUTE_SALE" and policy.route_sale_needs_invoice
        )
        if policy.dispatch_without_invoice == "OFF" or not judged:
            return DispatchCheckResponse(
                enforcement=policy.dispatch_without_invoice,
                message=None,
                would_block=False,
            )
        return DispatchCheckResponse(
            enforcement=policy.dispatch_without_invoice,
            message=(
                f"{note_number} is a {CHALLAN_REASONS[reason].lower()} with no "
                "invoice yet. GST requires the tax invoice at or before the "
                "goods leave (CGST s.31): use Dispatch and invoice, or give "
                "the challan a reason that allows invoicing later."
            ),
            would_block=policy.dispatch_without_invoice == "BLOCK",
        )

    def judge_dispatch(
        self, firm_id: UUID, *, note_number: str, challan_reason: str
    ) -> str | None:
        """Refuse a hand dispatch the policy blocks; return a warning otherwise.

        Raises:
            ValidationError: When the firm blocks dispatch before the invoice.

        """
        finding = self.dispatch_check(
            firm_id, note_number=note_number, challan_reason=challan_reason
        )
        if finding.would_block:
            raise ValidationError(finding.message or "")
        return finding.message
