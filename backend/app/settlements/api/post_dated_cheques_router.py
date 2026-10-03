"""Firm-scoped REST endpoints for the post-dated cheque register (ACC-2).

Two routers, one per direction: a customer's cheque is received money and
takes the receipt grants, the firm's own cheque to a supplier is money out and
takes the payment grants. The handlers are thin twins over shared helpers, so
the rules live once, in `PostDatedChequeService`.
"""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.concurrency import assert_version, parse_if_match, set_etag
from app.core.constants.core import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.settlements.models import SettlementDirection
from app.settlements.models.post_dated_cheque import PostDatedCheque
from app.settlements.schemas.post_dated_cheque import (
    PostDatedChequeBounce,
    PostDatedChequeCancel,
    PostDatedChequeClear,
    PostDatedChequeCreate,
    PostDatedChequeDeposit,
    PostDatedChequeResponse,
    PostDatedChequeStatusEnum,
)
from app.settlements.services.post_dated_cheques import PostDatedChequeService

received_cheques_router = APIRouter(
    prefix="/api/v1/post-dated-cheques/received",
    tags=["Post-dated cheques"],
    responses=STANDARD_ERROR_RESPONSES,
)
issued_cheques_router = APIRouter(
    prefix="/api/v1/post-dated-cheques/issued",
    tags=["Post-dated cheques"],
    responses=STANDARD_ERROR_RESPONSES,
)

ReceivedViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("RECEIPT_VIEW")]
ReceivedWriteScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("RECEIPT_CREATE")
]
IssuedViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("PAYMENT_VIEW")]
IssuedWriteScope = Annotated[ResolvedFirmScope, firm_permission_scope("PAYMENT_CREATE")]
StatusQuery = Annotated[PostDatedChequeStatusEnum | None, Query(alias="status")]
DateQuery = Annotated[date | None, Query()]
PartyQuery = Annotated[UUID | None, Query()]

_RECEIVED = SettlementDirection.RECEIPT
_ISSUED = SettlementDirection.PAYMENT


def _service(db: Session, direction: SettlementDirection) -> PostDatedChequeService:
    """Return the service for one direction."""
    return PostDatedChequeService(db, direction=direction)


def _one(
    service: PostDatedChequeService,
    row: PostDatedCheque,
    response: Response,
    message: str,
) -> ApiResponse[PostDatedChequeResponse]:
    """Answer with one cheque and publish its version."""
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0], message=message)


def _list(
    db: Session,
    direction: SettlementDirection,
    *,
    firm_id: UUID,
    page: int,
    page_size: int,
    search: str,
    status_filter: PostDatedChequeStatusEnum | None,
    party_id: UUID | None,
    due_on: date | None,
    cheque_from: date | None,
    cheque_to: date | None,
) -> PaginatedResponse[PostDatedChequeResponse]:
    """Return one page of one direction's register."""
    service = _service(db, direction)
    rows, total = service.list_cheques(
        firm_id=firm_id,
        page=page,
        page_size=page_size,
        status=None if status_filter is None else status_filter.value,
        party_id=party_id,
        due_on=due_on,
        date_from=cheque_from,
        date_to=cheque_to,
        search=search,
    )
    return PaginatedResponse(
        data=service.responses(rows),
        pagination=PaginationParams(page=page, page_size=page_size).metadata(total),
    )


def _committed(
    db: Session,
    service: PostDatedChequeService,
    row: PostDatedCheque,
    response: Response,
    message: str,
) -> ApiResponse[PostDatedChequeResponse]:
    """Commit a step in the cheque's life and answer with the cheque."""
    db.commit()
    db.refresh(row)
    return _one(service, row, response, message)


def _expecting(
    service: PostDatedChequeService,
    cheque_id: UUID,
    *,
    firm_id: UUID,
    expected_version: int | None,
) -> None:
    """Refuse a step aimed at a cheque somebody has moved on since it was read."""
    assert_version(service.get(cheque_id, firm_id=firm_id).version, expected_version)


# ----------------------------------------------------------------------
# A customer's cheques, received
# ----------------------------------------------------------------------


@received_cheques_router.get(
    "", response_model=PaginatedResponse[PostDatedChequeResponse]
)
def list_received_cheques(
    scope: ReceivedViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
    search: str = Query(default=""),
    status_filter: StatusQuery = None,
    party_id: PartyQuery = None,
    due_on: DateQuery = None,
    cheque_from: DateQuery = None,
    cheque_to: DateQuery = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[PostDatedChequeResponse]:
    """List customers' cheques in cheque-date order.

    ``due_on`` gives the cheques still held whose date has come by then: what
    can be banked that day.
    """
    return _list(
        db,
        _RECEIVED,
        firm_id=scope.firm_id,
        page=page,
        page_size=page_size,
        search=search,
        status_filter=status_filter,
        party_id=party_id,
        due_on=due_on,
        cheque_from=cheque_from,
        cheque_to=cheque_to,
    )


@received_cheques_router.post(
    "",
    response_model=ApiResponse[PostDatedChequeResponse],
    status_code=status.HTTP_201_CREATED,
)
def record_received_cheque(
    payload: PostDatedChequeCreate,
    scope: ReceivedWriteScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[PostDatedChequeResponse]:
    """Hold a customer's cheque dated ahead. Nothing is posted yet."""
    service = _service(db, _RECEIVED)
    row = service.create(payload, firm_id=scope.firm_id, actor_id=scope.actor_id)
    return _committed(db, service, row, response, "Cheque held until its date.")


@received_cheques_router.get(
    "/{cheque_id}", response_model=ApiResponse[PostDatedChequeResponse]
)
def get_received_cheque(
    cheque_id: UUID,
    scope: ReceivedViewScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[PostDatedChequeResponse]:
    """Return one customer's cheque."""
    service = _service(db, _RECEIVED)
    row = service.get(cheque_id, firm_id=scope.firm_id)
    return _one(service, row, response, "Cheque retrieved.")


@received_cheques_router.post(
    "/{cheque_id}/deposit", response_model=ApiResponse[PostDatedChequeResponse]
)
def deposit_received_cheque(
    cheque_id: UUID,
    payload: PostDatedChequeDeposit,
    scope: ReceivedWriteScope,
    response: Response,
    expected_version: Annotated[int | None, Depends(parse_if_match)],
    db: Session = Depends(get_db),
) -> ApiResponse[PostDatedChequeResponse]:
    """Bank a customer's cheque, which records and posts the receipt."""
    service = _service(db, _RECEIVED)
    _expecting(
        service,
        cheque_id,
        firm_id=scope.firm_id,
        expected_version=expected_version,
    )
    row = service.deposit(
        cheque_id, payload, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return _committed(db, service, row, response, "Cheque banked and posted.")


@received_cheques_router.post(
    "/{cheque_id}/clear", response_model=ApiResponse[PostDatedChequeResponse]
)
def clear_received_cheque(
    cheque_id: UUID,
    payload: PostDatedChequeClear,
    scope: ReceivedWriteScope,
    response: Response,
    expected_version: Annotated[int | None, Depends(parse_if_match)],
    db: Session = Depends(get_db),
) -> ApiResponse[PostDatedChequeResponse]:
    """Record that the bank honoured a customer's cheque."""
    service = _service(db, _RECEIVED)
    _expecting(
        service,
        cheque_id,
        firm_id=scope.firm_id,
        expected_version=expected_version,
    )
    row = service.clear(
        cheque_id,
        cleared_on=payload.cleared_on,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return _committed(db, service, row, response, "Cheque cleared.")


@received_cheques_router.post(
    "/{cheque_id}/bounce", response_model=ApiResponse[PostDatedChequeResponse]
)
def bounce_received_cheque(
    cheque_id: UUID,
    payload: PostDatedChequeBounce,
    scope: ReceivedWriteScope,
    response: Response,
    expected_version: Annotated[int | None, Depends(parse_if_match)],
    db: Session = Depends(get_db),
) -> ApiResponse[PostDatedChequeResponse]:
    """Record a customer's returned cheque: reversed, with its charges."""
    service = _service(db, _RECEIVED)
    _expecting(
        service,
        cheque_id,
        firm_id=scope.firm_id,
        expected_version=expected_version,
    )
    row = service.bounce(
        cheque_id, payload, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return _committed(db, service, row, response, "Cheque returned and reversed.")


@received_cheques_router.post(
    "/{cheque_id}/cancel", response_model=ApiResponse[PostDatedChequeResponse]
)
def cancel_received_cheque(
    cheque_id: UUID,
    payload: PostDatedChequeCancel,
    scope: ReceivedWriteScope,
    response: Response,
    expected_version: Annotated[int | None, Depends(parse_if_match)],
    db: Session = Depends(get_db),
) -> ApiResponse[PostDatedChequeResponse]:
    """Take a held customer's cheque out of the register."""
    service = _service(db, _RECEIVED)
    _expecting(
        service,
        cheque_id,
        firm_id=scope.firm_id,
        expected_version=expected_version,
    )
    row = service.cancel(
        cheque_id,
        reason=payload.reason,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return _committed(db, service, row, response, "Cheque cancelled.")


# ----------------------------------------------------------------------
# The firm's own cheques, issued to suppliers
# ----------------------------------------------------------------------


@issued_cheques_router.get(
    "", response_model=PaginatedResponse[PostDatedChequeResponse]
)
def list_issued_cheques(
    scope: IssuedViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
    search: str = Query(default=""),
    status_filter: StatusQuery = None,
    party_id: PartyQuery = None,
    due_on: DateQuery = None,
    cheque_from: DateQuery = None,
    cheque_to: DateQuery = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[PostDatedChequeResponse]:
    """List the firm's cheques to suppliers in cheque-date order."""
    return _list(
        db,
        _ISSUED,
        firm_id=scope.firm_id,
        page=page,
        page_size=page_size,
        search=search,
        status_filter=status_filter,
        party_id=party_id,
        due_on=due_on,
        cheque_from=cheque_from,
        cheque_to=cheque_to,
    )


@issued_cheques_router.post(
    "",
    response_model=ApiResponse[PostDatedChequeResponse],
    status_code=status.HTTP_201_CREATED,
)
def record_issued_cheque(
    payload: PostDatedChequeCreate,
    scope: IssuedWriteScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[PostDatedChequeResponse]:
    """Hold a cheque the firm wrote dated ahead. Nothing is posted yet."""
    service = _service(db, _ISSUED)
    row = service.create(payload, firm_id=scope.firm_id, actor_id=scope.actor_id)
    return _committed(db, service, row, response, "Cheque held until its date.")


@issued_cheques_router.get(
    "/{cheque_id}", response_model=ApiResponse[PostDatedChequeResponse]
)
def get_issued_cheque(
    cheque_id: UUID,
    scope: IssuedViewScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[PostDatedChequeResponse]:
    """Return one of the firm's cheques."""
    service = _service(db, _ISSUED)
    row = service.get(cheque_id, firm_id=scope.firm_id)
    return _one(service, row, response, "Cheque retrieved.")


@issued_cheques_router.post(
    "/{cheque_id}/deposit", response_model=ApiResponse[PostDatedChequeResponse]
)
def present_issued_cheque(
    cheque_id: UUID,
    payload: PostDatedChequeDeposit,
    scope: IssuedWriteScope,
    response: Response,
    expected_version: Annotated[int | None, Depends(parse_if_match)],
    db: Session = Depends(get_db),
) -> ApiResponse[PostDatedChequeResponse]:
    """Record the firm's cheque presented, which posts the payment."""
    service = _service(db, _ISSUED)
    _expecting(
        service,
        cheque_id,
        firm_id=scope.firm_id,
        expected_version=expected_version,
    )
    row = service.deposit(
        cheque_id, payload, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return _committed(db, service, row, response, "Cheque presented and posted.")


@issued_cheques_router.post(
    "/{cheque_id}/clear", response_model=ApiResponse[PostDatedChequeResponse]
)
def clear_issued_cheque(
    cheque_id: UUID,
    payload: PostDatedChequeClear,
    scope: IssuedWriteScope,
    response: Response,
    expected_version: Annotated[int | None, Depends(parse_if_match)],
    db: Session = Depends(get_db),
) -> ApiResponse[PostDatedChequeResponse]:
    """Record that the firm's cheque was paid by its bank."""
    service = _service(db, _ISSUED)
    _expecting(
        service,
        cheque_id,
        firm_id=scope.firm_id,
        expected_version=expected_version,
    )
    row = service.clear(
        cheque_id,
        cleared_on=payload.cleared_on,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return _committed(db, service, row, response, "Cheque cleared.")


@issued_cheques_router.post(
    "/{cheque_id}/bounce", response_model=ApiResponse[PostDatedChequeResponse]
)
def bounce_issued_cheque(
    cheque_id: UUID,
    payload: PostDatedChequeBounce,
    scope: IssuedWriteScope,
    response: Response,
    expected_version: Annotated[int | None, Depends(parse_if_match)],
    db: Session = Depends(get_db),
) -> ApiResponse[PostDatedChequeResponse]:
    """Record the firm's cheque returned unpaid: the payment is reversed."""
    service = _service(db, _ISSUED)
    _expecting(
        service,
        cheque_id,
        firm_id=scope.firm_id,
        expected_version=expected_version,
    )
    row = service.bounce(
        cheque_id, payload, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return _committed(db, service, row, response, "Cheque returned and reversed.")


@issued_cheques_router.post(
    "/{cheque_id}/cancel", response_model=ApiResponse[PostDatedChequeResponse]
)
def cancel_issued_cheque(
    cheque_id: UUID,
    payload: PostDatedChequeCancel,
    scope: IssuedWriteScope,
    response: Response,
    expected_version: Annotated[int | None, Depends(parse_if_match)],
    db: Session = Depends(get_db),
) -> ApiResponse[PostDatedChequeResponse]:
    """Take a held cheque of the firm's out of the register."""
    service = _service(db, _ISSUED)
    _expecting(
        service,
        cheque_id,
        firm_id=scope.firm_id,
        expected_version=expected_version,
    )
    row = service.cancel(
        cheque_id,
        reason=payload.reason,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return _committed(db, service, row, response, "Cheque cancelled.")
