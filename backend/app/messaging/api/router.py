"""Messaging: the firm's own settings page, the message log, and sending.

Settings are the firm administrator's: reading takes ``SETTINGS_VIEW`` and
changing ``SETTINGS_UPDATE``, as the firm's numbering series and print
templates do. Sending a document by hand, and resending, take
``DOCUMENT_SEND`` (§51, decision 5): printing shows what the screen shows,
sending acts for the firm towards somebody outside it. The log opens to either.

No route here is gated on a business-profile feature -- the owner decided on
2026-10-01 that messaging is a feature the firm turns on itself.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.common.scope import (
    ResolvedFirmScope,
    firm_any_permission_scope,
    firm_permission_scope,
)
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.messaging.events import EVENTS
from app.messaging.models import MessagingOutbox
from app.messaging.providers import ADAPTERS
from app.messaging.schemas import (
    ChannelAccountWrite,
    ChannelResponse,
    EventConfigResponse,
    EventConfigWrite,
    HandShareRecord,
    HandShareResponse,
    ManualSendRequest,
    MessageResponse,
    MessageStatus,
    MessagingChannel,
    MessagingEventResponse,
    MessagingSettingsResponse,
    MessagingSettingsWrite,
    ProviderFieldResponse,
    ProviderResponse,
    ReminderRequest,
)
from app.messaging.services import MessagingService
from app.messaging.services.hand_share import HandShareService
from app.messaging.services.reminders import ReminderService

router = APIRouter(
    prefix="/api/v1/messaging",
    tags=["Messaging"],
    responses=STANDARD_ERROR_RESPONSES,
)

SettingsViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("SETTINGS_VIEW")]
SettingsUpdateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SETTINGS_UPDATE")
]
SendScope = Annotated[ResolvedFirmScope, firm_permission_scope("DOCUMENT_SEND")]
LogScope = Annotated[
    ResolvedFirmScope, firm_any_permission_scope("DOCUMENT_SEND", "SETTINGS_VIEW")
]


def _message(row: MessagingOutbox) -> MessageResponse:
    """Describe one message; a column read, no query."""
    return MessageResponse.model_validate(row)


@router.get("/settings", response_model=ApiResponse[MessagingSettingsResponse])
def get_messaging_settings(
    scope: SettingsViewScope, db: Session = Depends(get_db)
) -> ApiResponse[MessagingSettingsResponse]:
    """Report whether messaging is on for this firm, and the reminder schedule."""
    return ApiResponse(data=MessagingService(db).settings_response(scope.firm_id))


@router.put("/settings", response_model=ApiResponse[MessagingSettingsResponse])
def update_messaging_settings(
    data: MessagingSettingsWrite,
    scope: SettingsUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[MessagingSettingsResponse]:
    """Switch messaging on or off for this firm, or change the schedule."""
    return ApiResponse(
        data=MessagingService(db).update_settings(
            data, firm_id=scope.firm_id, actor_id=scope.actor_id
        ),
        message="Messaging settings saved.",
    )


@router.get("/providers", response_model=ApiResponse[list[ProviderResponse]])
def list_messaging_providers(
    _: SettingsViewScope,
) -> ApiResponse[list[ProviderResponse]]:
    """List every provider and the fields its account form needs."""
    return ApiResponse(
        data=[
            ProviderResponse(
                provider=adapter.provider,
                channel=adapter.channel,
                label=adapter.label,
                supports_status=adapter.supports_status,
                fields=[
                    ProviderFieldResponse(
                        name=field.name,
                        label=field.label,
                        secret=field.secret,
                        required=field.required,
                        kind=field.kind,
                        help=field.help,
                        choices=list(field.choices),
                        default=field.default,
                    )
                    for field in adapter.required_fields()
                ],
            )
            for adapter in ADAPTERS.values()
        ]
    )


@router.get("/events", response_model=ApiResponse[list[MessagingEventResponse]])
def list_messaging_events(
    _: SettingsViewScope,
) -> ApiResponse[list[MessagingEventResponse]]:
    """List every event a firm may send on, with the variables it offers."""
    return ApiResponse(
        data=[
            MessagingEventResponse(
                code=event.code,
                label=event.label,
                document_type=event.document_type,
                variables=list(event.variables),
                is_reminder=event.is_reminder,
                attaches_pdf=event.attaches_pdf,
                default_subject=event.default_subject,
                default_body=event.default_body,
            )
            for event in EVENTS
        ]
    )


@router.get("/channels", response_model=ApiResponse[list[ChannelResponse]])
def list_messaging_channels(
    scope: SettingsViewScope, db: Session = Depends(get_db)
) -> ApiResponse[list[ChannelResponse]]:
    """Report each channel: provider, health, whether it is on. Never a secret."""
    return ApiResponse(data=MessagingService(db).channels(scope.firm_id))


@router.put("/channels/{channel}", response_model=ApiResponse[ChannelResponse])
def save_messaging_channel(
    channel: MessagingChannel,
    data: ChannelAccountWrite,
    scope: SettingsUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ChannelResponse]:
    """Save or replace a channel's provider account; it must be tested again."""
    return ApiResponse(
        data=MessagingService(db).save_account(
            channel, data, firm_id=scope.firm_id, actor_id=scope.actor_id
        ),
        message="Account saved. Test it before switching the channel on.",
    )


@router.post("/channels/{channel}/test", response_model=ApiResponse[ChannelResponse])
def test_messaging_channel(
    channel: MessagingChannel,
    scope: SettingsUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ChannelResponse]:
    """Check the saved account with the provider; nobody is messaged."""
    result = MessagingService(db).test_channel(
        channel, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(
        data=result,
        message=(
            "Test passed."
            if result.health == "OK"
            else f"Test failed: {result.last_error}"
        ),
    )


@router.post("/channels/{channel}/enable", response_model=ApiResponse[ChannelResponse])
def enable_messaging_channel(
    channel: MessagingChannel,
    scope: SettingsUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ChannelResponse]:
    """Switch a channel on. Refused until its Test has passed."""
    return ApiResponse(
        data=MessagingService(db).set_channel_enabled(
            channel, True, firm_id=scope.firm_id, actor_id=scope.actor_id
        )
    )


@router.post("/channels/{channel}/disable", response_model=ApiResponse[ChannelResponse])
def disable_messaging_channel(
    channel: MessagingChannel,
    scope: SettingsUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ChannelResponse]:
    """Switch a channel off."""
    return ApiResponse(
        data=MessagingService(db).set_channel_enabled(
            channel, False, firm_id=scope.firm_id, actor_id=scope.actor_id
        )
    )


@router.get("/event-configs", response_model=ApiResponse[list[EventConfigResponse]])
def list_messaging_event_configs(
    scope: SettingsViewScope, db: Session = Depends(get_db)
) -> ApiResponse[list[EventConfigResponse]]:
    """Report which events send, on which channels, with which templates."""
    return ApiResponse(data=MessagingService(db).event_configs(scope.firm_id))


@router.put(
    "/event-configs/{event_code}", response_model=ApiResponse[EventConfigResponse]
)
def save_messaging_event_config(
    event_code: str,
    data: EventConfigWrite,
    scope: SettingsUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[EventConfigResponse]:
    """Replace one event's channels; their order is the fallback order."""
    return ApiResponse(
        data=MessagingService(db).save_event_config(
            event_code, data, firm_id=scope.firm_id, actor_id=scope.actor_id
        ),
        message="Saved.",
    )


@router.get("/messages", response_model=PaginatedResponse[MessageResponse])
def list_messages(
    scope: LogScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: str | None = None,
    status_value: Annotated[MessageStatus | None, Query(alias="status")] = None,
    channel: MessagingChannel | None = None,
    event_code: str | None = None,
    document_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[MessageResponse]:
    """List the firm's messages, newest first: sent, failed, skipped, queued."""
    params = PaginationParams(page=page, page_size=page_size)
    rows, total = MessagingService(db).list_messages(
        scope.firm_id,
        page=params.page,
        page_size=params.page_size,
        status=status_value,
        channel=channel,
        event_code=event_code,
        document_id=document_id,
        search=search,
    )
    return PaginatedResponse(
        data=[_message(row) for row in rows], pagination=params.metadata(total)
    )


@router.post(
    "/send",
    response_model=ApiResponse[MessageResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
def send_document(
    data: ManualSendRequest,
    scope: SendScope,
    db: Session = Depends(get_db),
) -> ApiResponse[MessageResponse]:
    """Queue one document to be sent now; the log shows when it went."""
    row = MessagingService(db).send_document(
        data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=_message(row), message="Queued to send.")


@router.get(
    "/share/sales-invoices/{invoice_id}",
    response_model=ApiResponse[HandShareResponse],
)
def prepare_hand_share(
    invoice_id: UUID,
    scope: SendScope,
    db: Session = Depends(get_db),
) -> ApiResponse[HandShareResponse]:
    """Say whom to share a bill with on WhatsApp by hand, and what to say.

    Needs no messaging account and no switch: the person sends it from their
    own WhatsApp (MSG-1).
    """
    return ApiResponse(
        data=HandShareService(db).prepare(invoice_id, firm_id=scope.firm_id)
    )


@router.get(
    "/share/customer-statements/{customer_id}",
    response_model=ApiResponse[HandShareResponse],
)
def prepare_reminder_share(
    customer_id: UUID,
    scope: SendScope,
    db: Session = Depends(get_db),
) -> ApiResponse[HandShareResponse]:
    """Say whom to remind on WhatsApp by hand, and what to say (MSG-3)."""
    return ApiResponse(
        data=ReminderService(db).prepare_whatsapp(customer_id, firm_id=scope.firm_id)
    )


@router.post(
    "/remind",
    response_model=ApiResponse[MessageResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
def remind_customer(
    data: ReminderRequest,
    scope: SendScope,
    db: Session = Depends(get_db),
) -> ApiResponse[MessageResponse]:
    """Email a customer their statement as a payment reminder (MSG-3)."""
    row = ReminderService(db).remind_by_email(
        data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=_message(row), message="Queued to send.")


@router.post(
    "/shared",
    response_model=ApiResponse[None],
    status_code=status.HTTP_201_CREATED,
)
def record_hand_share(
    data: HandShareRecord,
    scope: SendScope,
    db: Session = Depends(get_db),
) -> ApiResponse[None]:
    """Put a share made by hand on the document's timeline."""
    HandShareService(db).record(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    return ApiResponse(data=None, message="Recorded on the timeline.")


@router.post(
    "/messages/{message_id}/resend",
    response_model=ApiResponse[MessageResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
def resend_message(
    message_id: UUID,
    scope: SendScope,
    db: Session = Depends(get_db),
) -> ApiResponse[MessageResponse]:
    """Send a message again -- the only way any message goes twice."""
    row = MessagingService(db).resend(
        message_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=_message(row), message="Queued to send again.")
