"""Firm-scoped REST endpoints for GST returns.

The returns are read-only: a return is a view of the documents, and filing
happens on the authority's portal. Paying the tax is not (backlog 63): the
month's set-off and challan are recorded here and post to the books.
"""

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.scope import (
    ResolvedFirmScope,
    firm_any_permission_scope,
    firm_permission_scope,
)
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.responses.models import ApiResponse
from app.gst_returns.models import HEADS, GstPayment
from app.gst_returns.schemas import (
    GstHeadRow,
    GstPaymentCreate,
    GstPaymentPreviewResponse,
    GstPaymentResponse,
    GstPaymentReverse,
    GstUtilisationRow,
)
from app.gst_returns.services import GstReturnService
from app.gst_returns.services.gst_payment_service import (
    GstPaymentPreview,
    GstPaymentService,
)

router = APIRouter(
    prefix="/api/v1/gst-returns",
    tags=["GST Returns"],
    responses=STANDARD_ERROR_RESPONSES,
)

#: Reading a return means reading every sale of the period, so it is gated on
#: the same authority as the sales register rather than on a new code nobody
#: would think to grant.
GstReturnScope = Annotated[ResolvedFirmScope, firm_permission_scope("SALES_VIEW")]


@router.get("/gstr1", response_model=ApiResponse[dict[str, object]])
def gstr1(
    scope: GstReturnScope,
    from_date: Annotated[date, Query()],
    to_date: Annotated[date, Query()],
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, object]]:
    """Return the outward supplies for a period, section by section."""
    return ApiResponse(
        data=GstReturnService(db).gstr1(
            firm_scope=scope.firm_id, from_date=from_date, to_date=to_date
        )
    )


@router.get("/gstr3b", response_model=ApiResponse[dict[str, object]])
def gstr3b(
    scope: GstReturnScope,
    from_date: Annotated[date, Query()],
    to_date: Annotated[date, Query()],
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, object]]:
    """Return the outward half of the summary return for a period."""
    return ApiResponse(
        data=GstReturnService(db).gstr3b(
            firm_scope=scope.firm_id, from_date=from_date, to_date=to_date
        )
    )


#: Reading what a month owes is reading the books or the sales.
GstPaymentViewScope = Annotated[
    ResolvedFirmScope, firm_any_permission_scope("ACCOUNT_VIEW", "SALES_VIEW")
]
#: Recording or reversing a challan posts a journal, so it takes the code
#: that posting a journal takes -- not a new one nobody would think to grant.
GstPaymentPostScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("JOURNAL_POST")
]


def _opening(
    igst: Decimal | None,
    cgst: Decimal | None,
    sgst: Decimal | None,
    cess: Decimal | None,
) -> dict[str, Decimal] | None:
    values = {"igst": igst, "cgst": cgst, "sgst": sgst, "cess": cess}
    if all(value is None for value in values.values()):
        return None
    return {head: value or Decimal("0") for head, value in values.items()}


def _preview_response(preview: GstPaymentPreview) -> GstPaymentPreviewResponse:
    result = preview.set_off
    return GstPaymentPreviewResponse(
        return_period=preview.return_period,
        due_date=preview.due_date,
        previous_settled=preview.previous_settled,
        days_late=preview.days_late,
        suggested_interest=preview.suggested_interest,
        cash_total=preview.cash_total,
        heads=[
            GstHeadRow(
                head=head.upper(),
                liability=result.liability[head],
                credit_brought_forward=preview.brought_forward[head],
                credit_available=result.credit[head],
                paid_by_credit=result.paid_by_credit(head),
                cash=result.cash(head),
                credit_used=result.used(head),
                carried_forward=result.carried(head),
            )
            for head in HEADS
        ],
        utilisation=[
            GstUtilisationRow(
                credit_head=source.upper(), liability_head=target.upper(), amount=amount
            )
            for (source, target), amount in result.utilised.items()
        ],
    )


def _payment_response(row: GstPayment) -> GstPaymentResponse:
    heads = [
        GstHeadRow(
            head=head.upper(),
            liability=getattr(row, f"liability_{head}"),
            credit_brought_forward=Decimal("0"),
            credit_available=getattr(row, f"credit_{head}"),
            paid_by_credit=getattr(row, f"liability_{head}")
            - getattr(row, f"cash_{head}"),
            cash=getattr(row, f"cash_{head}"),
            credit_used=getattr(row, f"used_{head}"),
            carried_forward=getattr(row, f"carried_{head}"),
        )
        for head in HEADS
    ]
    return GstPaymentResponse(
        id=row.id,
        return_period=row.return_period,
        payment_date=row.payment_date,
        status=row.status,
        challan_cpin=row.challan_cpin,
        challan_cin=row.challan_cin,
        money_account_id=row.money_account_id,
        heads=heads,
        cash_total=sum((h.cash for h in heads), Decimal("0")),
        interest_amount=row.interest_amount,
        late_fee_amount=row.late_fee_amount,
        narration=row.narration,
        journal_entry_id=row.journal_entry_id,
        reversal_journal_entry_id=row.reversal_journal_entry_id,
        reversal_reason=row.reversal_reason,
        reversed_at=row.reversed_at,
        version=row.version,
    )


@router.get("/payments/preview", response_model=ApiResponse[GstPaymentPreviewResponse])
def gst_payment_preview(
    scope: GstPaymentViewScope,
    return_period: Annotated[str, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")],
    payment_date: date | None = None,
    opening_credit_igst: Decimal | None = None,
    opening_credit_cgst: Decimal | None = None,
    opening_credit_sgst: Decimal | None = None,
    opening_credit_cess: Decimal | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[GstPaymentPreviewResponse]:
    """Work out a month's set-off and cash payable; writes nothing (63)."""
    preview = GstPaymentService(db).preview(
        scope.firm_id,
        return_period,
        payment_date=payment_date,
        opening_credit=_opening(
            opening_credit_igst,
            opening_credit_cgst,
            opening_credit_sgst,
            opening_credit_cess,
        ),
    )
    return ApiResponse(data=_preview_response(preview))


@router.get("/payments", response_model=ApiResponse[list[GstPaymentResponse]])
def list_gst_payments(
    scope: GstPaymentViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[GstPaymentResponse]]:
    """Every month the firm has recorded as settled, newest first."""
    return ApiResponse(
        data=[
            _payment_response(row)
            for row in GstPaymentService(db).list_payments(scope.firm_id)
        ]
    )


@router.post("/payments", response_model=ApiResponse[GstPaymentResponse])
def record_gst_payment(
    data: GstPaymentCreate,
    scope: GstPaymentPostScope,
    db: Session = Depends(get_db),
) -> ApiResponse[GstPaymentResponse]:
    """Record a month's challan: set-off and cash, posted in one journal."""
    row = GstPaymentService(db).record(
        scope.firm_id,
        data.return_period,
        payment_date=data.payment_date,
        money_account_id=data.money_account_id,
        actor_id=scope.actor_id,
        challan_cpin=data.challan_cpin,
        challan_cin=data.challan_cin,
        interest_amount=data.interest_amount,
        interest_account_id=data.interest_account_id,
        late_fee_amount=data.late_fee_amount,
        late_fee_account_id=data.late_fee_account_id,
        opening_credit=_opening(
            data.opening_credit_igst,
            data.opening_credit_cgst,
            data.opening_credit_sgst,
            data.opening_credit_cess,
        ),
        narration=data.narration,
    )
    db.commit()
    return ApiResponse(data=_payment_response(row))


@router.post(
    "/payments/{payment_id}/reverse", response_model=ApiResponse[GstPaymentResponse]
)
def reverse_gst_payment(
    payment_id: UUID,
    data: GstPaymentReverse,
    scope: GstPaymentPostScope,
    db: Session = Depends(get_db),
) -> ApiResponse[GstPaymentResponse]:
    """Take back the latest month's settlement, posting the mirror journal."""
    row = GstPaymentService(db).reverse(
        payment_id, firm_id=scope.firm_id, actor_id=scope.actor_id, reason=data.reason
    )
    db.commit()
    return ApiResponse(data=_payment_response(row))
