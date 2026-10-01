"""WhatsApp through Meta's Cloud API, directly -- no partner in between.

Every business-initiated WhatsApp message is a **template Meta approved**; the
firm creates and gets them approved in its own WhatsApp Manager, and names one
per event on the Messaging page. Billing messages are the *Utility* category.
What goes out is the template with its variables filled in, in order:
``{{1}}`` is the first variable the event offers, ``{{2}}`` the second.

**Status.** The Cloud API reports delivered and read only by webhook, and the
server cannot receive one (§51). A WhatsApp message therefore stays *sent*;
``fetch_status`` says so by answering ``None``.
"""

from app.messaging.providers.base import (
    MessagingAdapter,
    OutgoingMessage,
    ProviderError,
    ProviderField,
    SendResult,
    scrub,
)
from app.messaging.providers.http import request_json

GRAPH_URL = "https://graph.facebook.com/v21.0"


def whatsapp_number(phone: str) -> str:
    """Return a number as the Cloud API wants it: digits with country code."""
    return "".join(character for character in phone if character.isdigit())


class WhatsAppCloudAdapter(MessagingAdapter):
    """Send WhatsApp template messages through the Meta Cloud API."""

    provider = "META_CLOUD"
    channel = "WHATSAPP"
    label = "WhatsApp (Meta Cloud API)"

    @classmethod
    def required_fields(cls) -> tuple[ProviderField, ...]:
        """Return the fields a Cloud API account needs."""
        return (
            ProviderField(
                "phone_number_id",
                "Phone number ID",
                help="WhatsApp Manager > API setup: the ID, not the number.",
            ),
            ProviderField(
                "business_account_id",
                "WhatsApp Business account ID",
                required=False,
            ),
            ProviderField(
                "access_token",
                "Access token",
                secret=True,
                kind="password",
                help="A permanent token for a system user, not the 24-hour one.",
            ),
        )

    def _headers(self) -> dict[str, str]:
        """Return the bearer header."""
        return {"Authorization": f"Bearer {self.setting('access_token')}"}

    def test_connection(self) -> None:
        """Read the phone number's own record: proves the token and the ID."""
        phone_number_id = self.setting("phone_number_id")
        if not phone_number_id or not self.setting("access_token"):
            raise ProviderError(
                "Enter the phone number ID and the access token.", permanent=True
            )
        try:
            request_json(
                "GET",
                f"{GRAPH_URL}/{phone_number_id}"
                "?fields=display_phone_number,verified_name",
                headers=self._headers(),
            )
        except ProviderError as error:
            raise ProviderError(
                scrub(error.message, self.secret_values()), permanent=error.permanent
            ) from error

    def send(self, message: OutgoingMessage) -> SendResult:
        """Send one template message."""
        if not message.template_name:
            raise ProviderError(
                "No WhatsApp template is named for this event; WhatsApp only "
                "delivers templates Meta has approved.",
                permanent=True,
            )
        template: dict[str, object] = {
            "name": message.template_name,
            "language": {"code": message.template_language or "en"},
        }
        if message.variables:
            template["components"] = [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": value} for value in message.variables
                    ],
                }
            ]
        try:
            response = request_json(
                "POST",
                f"{GRAPH_URL}/{self.setting('phone_number_id')}/messages",
                headers=self._headers(),
                payload={
                    "messaging_product": "whatsapp",
                    "to": whatsapp_number(message.to),
                    "type": "template",
                    "template": template,
                },
            )
        except ProviderError as error:
            raise ProviderError(
                scrub(error.message, self.secret_values()), permanent=error.permanent
            ) from error
        identifier = None
        if isinstance(response.body, dict):
            messages = response.body.get("messages")
            if isinstance(messages, list) and messages:
                first = messages[0]
                if isinstance(first, dict):
                    identifier = first.get("id")
        return SendResult(
            provider_message_id=None if identifier is None else str(identifier)
        )
