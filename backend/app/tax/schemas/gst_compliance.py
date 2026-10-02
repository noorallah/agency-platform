"""A firm's GST document policy (backlog 77 rows 1-2, decision A35)."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from app.tax.schemas.tax_framework import TaxFrameworkSchema

DispatchWithoutInvoice = Literal["OFF", "WARN", "BLOCK"]
ItcClaimBasis = Literal["ALL", "MATCHED_ONLY"]


class GstComplianceSettingsResponse(TaxFrameworkSchema):
    """The firm's policy, and whether the firm actually chose it."""

    einvoice_applicable_from: date | None
    thirty_day_rule_from: date | None
    dispatch_without_invoice: DispatchWithoutInvoice
    route_sale_needs_invoice: bool
    #: Whether 3B claims every bill or only those matched to GSTR-2B (78.3).
    itc_claim_basis: ItcClaimBasis = "ALL"
    #: How far a bill's tax may differ from 2B and still match, in rupees.
    gstr2b_tolerance: Decimal = Decimal("1.00")
    #: Above this a consignment needs an e-way bill (77 row 10).
    eway_bill_limit: Decimal = Decimal("50000")
    is_configured: bool


class GstComplianceSettingsWrite(TaxFrameworkSchema):
    """Replace the firm's policy. Every field is sent every time."""

    einvoice_applicable_from: date | None
    thirty_day_rule_from: date | None
    dispatch_without_invoice: DispatchWithoutInvoice
    route_sale_needs_invoice: bool
    #: Absent keeps the firm's own (78.3): a client that never showed it
    #: cannot reset it.
    itc_claim_basis: ItcClaimBasis | None = None
    gstr2b_tolerance: Decimal | None = Field(
        default=None, ge=0, le=1000, max_digits=18, decimal_places=2
    )
    #: Absent keeps the firm's own, as the two above.
    eway_bill_limit: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )

    @model_validator(mode="after")
    def _thirty_days_follow_einvoicing(self) -> "GstComplianceSettingsWrite":
        """Refuse a 30-day limit on a firm that does not e-invoice."""
        if self.thirty_day_rule_from is None:
            return self
        if self.einvoice_applicable_from is None:
            raise ValueError(
                "The 30-day limit applies only to a firm that e-invoices: set "
                "the date e-invoicing applies from first."
            )
        if self.thirty_day_rule_from < self.einvoice_applicable_from:
            raise ValueError("The 30-day limit cannot start before e-invoicing does.")
        return self


class DispatchCheckResponse(TaxFrameworkSchema):
    """What dispatching one delivery note by hand would meet."""

    #: The firm's policy: OFF, WARN or BLOCK.
    enforcement: DispatchWithoutInvoice
    #: Why the rule applies to this note; null when it does not.
    message: str | None
    #: True when dispatching it by hand would be refused.
    would_block: bool
