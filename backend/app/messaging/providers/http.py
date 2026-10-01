"""A small JSON-over-HTTPS client on the standard library.

``urllib`` rather than a new dependency: the release is compiled and every
package added has to survive that, and two providers' worth of POSTs does not
justify one. Tests replace :data:`transport` rather than reaching a network.
"""

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from app.messaging.providers.base import ProviderError

#: Seconds a provider gets to answer before the attempt counts as failed.
TIMEOUT_SECONDS = 20


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """A provider's answer: the status and the parsed body, if it was JSON."""

    status: int
    body: object
    text: str


def _urllib_transport(
    method: str, url: str, headers: Mapping[str, str], data: bytes | None
) -> HttpResponse:
    """Send one request with urllib and read the whole answer."""
    request = urllib.request.Request(  # noqa: S310 - https URLs built in code
        url, data=data, method=method, headers=dict(headers)
    )
    try:
        with urllib.request.urlopen(  # noqa: S310
            request, timeout=TIMEOUT_SECONDS
        ) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status = int(response.status)
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        status = int(error.code)
    try:
        body: object = json.loads(raw) if raw else None
    except ValueError:
        body = None
    return HttpResponse(status=status, body=body, text=raw)


#: Replaced in tests; never reaches a network there.
transport: Callable[[str, str, Mapping[str, str], bytes | None], HttpResponse] = (
    _urllib_transport
)


def request_json(
    method: str,
    url: str,
    *,
    headers: Mapping[str, str],
    payload: object | None = None,
) -> HttpResponse:
    """Send a JSON request; raise a :class:`ProviderError` for any failure.

    A 4xx other than 408 and 429 is the provider refusing what was asked --
    bad credentials, an unknown template -- and retrying cannot change it, so
    it is permanent. A timeout, a refused connection, 408, 429 and 5xx are
    transient. The URL is never put in the message: MSG91 carries its key in
    one.
    """
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    all_headers = {"Accept": "application/json", **headers}
    if data is not None:
        all_headers["Content-Type"] = "application/json"
    try:
        response = transport(method, url, all_headers, data)
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        reason = getattr(error, "reason", None) or type(error).__name__
        raise ProviderError(
            f"Could not reach the provider: {reason}.", permanent=False
        ) from error
    if response.status >= 400:
        transient = response.status in {408, 429} or response.status >= 500
        raise ProviderError(
            f"The provider answered {response.status}: "
            f"{_provider_message(response)}",
            permanent=not transient,
        )
    return response


def _provider_message(response: HttpResponse) -> str:
    """Pull the provider's own reason out of an error body."""
    body = response.body
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            message = error.get("message") or error.get("error_user_msg")
            if message:
                return str(message)
        for key in ("message", "msg", "error", "type"):
            if body.get(key):
                return str(body[key])
    return response.text[:300] or "no reason given."
