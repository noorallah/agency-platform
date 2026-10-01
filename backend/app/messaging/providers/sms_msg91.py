"""SMS through MSG91, on the firm's own DLT registration.

TRAI requires every commercial SMS in India to come from a registered sender
(the 6-character header) with a registered template. That paperwork is the
firm's: it registers on a DLT portal, then adds the same template in MSG91,
which gives it a template id. The firm enters its MSG91 auth key and sender id
once, and the template id per event on the Messaging page.

The template's variables are filled in order: ``var1`` is the first variable
the event offers, ``var2`` the second -- name them that way in MSG91.

**Status.** Delivery reports come from MSG91 by webhook, which the server
cannot receive (§51); an SMS therefore stays *sent*.
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

FLOW_URL = "https://control.msg91.com/api/v5/flow/"
BALANCE_URL = "https://control.msg91.com/api/balance.php"


def sms_number(phone: str) -> str:
    """Return a number with its country code and no plus: ``91XXXXXXXXXX``."""
    digits = "".join(character for character in phone if character.isdigit())
    return f"91{digits}" if len(digits) == 10 else digits


class Msg91Adapter(MessagingAdapter):
    """Send DLT-registered SMS templates through MSG91."""

    provider = "MSG91"
    channel = "SMS"
    label = "SMS (MSG91)"

    @classmethod
    def required_fields(cls) -> tuple[ProviderField, ...]:
        """Return the fields an MSG91 account needs."""
        return (
            ProviderField(
                "authkey",
                "Auth key",
                secret=True,
                kind="password",
                help="MSG91 > API > Auth key.",
            ),
            ProviderField(
                "sender_id",
                "DLT sender ID",
                help="The 6-letter header registered on DLT.",
            ),
            ProviderField(
                "dlt_entity_id",
                "DLT principal entity ID",
                required=False,
                help="For your records; MSG91 holds it against the sender.",
            ),
        )

    def _headers(self) -> dict[str, str]:
        """Return the auth header the flow API reads the key from.

        The balance check takes the key in its URL instead, which is why
        ``request_json`` never puts a URL into an error message.
        """
        return {"authkey": self.setting("authkey")}

    def test_connection(self) -> None:
        """Ask MSG91 for the transactional balance: proves the key."""
        if not self.setting("authkey") or not self.setting("sender_id"):
            raise ProviderError("Enter the auth key and the sender ID.", permanent=True)
        if len(self.setting("sender_id")) != 6:
            raise ProviderError(
                "A DLT sender ID is exactly 6 characters.", permanent=True
            )
        try:
            response = request_json(
                "GET",
                f"{BALANCE_URL}?type=4&authkey={self.setting('authkey')}",
                headers=self._headers(),
            )
        except ProviderError as error:
            raise ProviderError(
                scrub(error.message, self.secret_values()), permanent=error.permanent
            ) from error
        body = response.body
        if isinstance(body, dict) and str(body.get("type", "")).lower() == "error":
            raise ProviderError(
                scrub(
                    f"MSG91 refused the key: {body.get('message') or body}",
                    self.secret_values(),
                ),
                permanent=True,
            )

    def send(self, message: OutgoingMessage) -> SendResult:
        """Send one templated SMS through MSG91's flow API."""
        if not message.template_name:
            raise ProviderError(
                "No MSG91 template id is named for this event; an SMS in India "
                "must use a DLT-registered template.",
                permanent=True,
            )
        recipient: dict[str, str] = {"mobiles": sms_number(message.to)}
        for position, value in enumerate(message.variables, start=1):
            recipient[f"var{position}"] = value
        try:
            response = request_json(
                "POST",
                FLOW_URL,
                headers=self._headers(),
                payload={
                    "template_id": message.template_name,
                    "sender": self.setting("sender_id"),
                    "short_url": "0",
                    "recipients": [recipient],
                },
            )
        except ProviderError as error:
            raise ProviderError(
                scrub(error.message, self.secret_values()), permanent=error.permanent
            ) from error
        body = response.body
        if isinstance(body, dict) and str(body.get("type", "")).lower() == "error":
            raise ProviderError(
                scrub(
                    f"MSG91 refused the message: {body.get('message')}",
                    self.secret_values(),
                ),
                permanent=True,
            )
        identifier = body.get("message") if isinstance(body, dict) else None
        return SendResult(
            provider_message_id=None if identifier is None else str(identifier)
        )
