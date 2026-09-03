"""The government portal, and a sandbox that stands in for it.

One protocol, two implementations, and the choice is a firm's configuration
rather than a branch inside the service. That keeps every rule about *when* a
document may be registered in one place, and leaves the transport to be swapped
without touching it.

**The sandbox is a rehearsal and says so in every value it returns.** Its IRN
begins `SBX`, its acknowledgement number begins `SBX`, and the row it lands on
records `mode = SANDBOX` for ever. Nothing filed a return; nothing at the
authority knows this invoice. A sandbox reference that looked like a real one
is a document somebody eventually presents at a check post, which is the one
failure this module is built to make impossible.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Protocol

from app.core.utils.dates import utc_now


@dataclass(frozen=True, slots=True)
class PortalResult:
    """What the portal said, refusal included.

    A refusal is a result rather than an exception: the portal answering "this
    invoice number is already registered" is information the person fixing the
    invoice needs on the invoice, not a stack trace.
    """

    ok: bool
    reference: str | None = None
    acknowledgement_number: str | None = None
    signed_qr_code: str | None = None
    signed_document: str | None = None
    valid_until: date | None = None
    error_code: str | None = None
    error_message: str | None = None


class InvoiceRegistrationPortal(Protocol):
    """What this module needs from whatever registers its documents."""

    def register_invoice(self, payload: dict[str, object]) -> PortalResult:
        """Register one invoice and return its reference."""
        ...

    def cancel_invoice(self, reference: str, *, reason: str) -> PortalResult:
        """Withdraw a registration."""
        ...

    def generate_eway_bill(self, payload: dict[str, object]) -> PortalResult:
        """Raise an e-way bill for a consignment."""
        ...

    def cancel_eway_bill(self, reference: str, *, reason: str) -> PortalResult:
        """Withdraw an e-way bill."""
        ...


class SandboxPortal:
    """A portal that answers plausibly and files nothing.

    Deterministic on purpose: the same payload gives the same reference every
    time, so two runs of the seed or the tests can be compared. A random one
    would make every run a different database.

    It refuses the same things the real portal refuses that can be judged
    without the authority's records -- a duplicate document number within this
    process, and a payload missing what the schema requires. It cannot know
    that a GSTIN is suspended or that a return is blocked, and does not
    pretend to: that is the gap a firm crosses by switching to LIVE.
    """

    #: How long an e-way bill lasts, by distance. The real portal decides
    #: this; the sandbox uses the published rule so a screen showing an expiry
    #: shows a plausible one.
    _KM_PER_DAY = Decimal("200")

    def __init__(self) -> None:
        """Start with nothing registered."""
        self._seen: set[str] = set()

    @staticmethod
    def _digest(payload: dict[str, object]) -> str:
        """Return a stable 64-character hash of a payload."""
        canonical = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def register_invoice(self, payload: dict[str, object]) -> PortalResult:
        """Mint a sandbox IRN for a payload that carries what it must."""
        document = payload.get("DocDtls")
        number = (str(document.get("No")) if isinstance(document, dict) else "") or ""
        if not number:
            return PortalResult(
                ok=False,
                error_code="2150",
                error_message="The payload names no document number.",
            )
        if number in self._seen:
            # The real portal answers 2150 for a duplicate. Worth mimicking,
            # because a firm that re-registers is the ordinary mistake and the
            # message is what tells them so.
            return PortalResult(
                ok=False,
                error_code="2150",
                error_message=(
                    f"Document {number} is already registered. "
                    "Cancel the existing registration before raising another."
                ),
            )
        self._seen.add(number)
        digest = self._digest(payload)
        stamped = utc_now()
        return PortalResult(
            ok=True,
            # `SBX` first, so the reference says what it is even printed on
            # its own with no row beside it.
            reference=f"SBX{digest}"[:64],
            acknowledgement_number=f"SBX{digest[:12].upper()}",
            signed_qr_code=(
                f"SANDBOX.{digest[:24]}.{stamped.strftime('%Y%m%d%H%M%S')}"
            ),
            signed_document=f"SANDBOX.{digest}",
        )

    def cancel_invoice(self, reference: str, *, reason: str) -> PortalResult:
        """Accept a withdrawal, as the portal does inside its window."""
        if not reason.strip():
            return PortalResult(
                ok=False,
                error_code="2189",
                error_message="A cancellation needs a reason.",
            )
        return PortalResult(ok=True, reference=reference)

    def generate_eway_bill(self, payload: dict[str, object]) -> PortalResult:
        """Mint a sandbox e-way bill number and a plausible expiry."""
        distance = Decimal(str(payload.get("TransDistance", 0) or 0))
        if distance <= 0:
            return PortalResult(
                ok=False,
                error_code="102",
                error_message="An e-way bill needs the distance to be covered.",
            )
        digest = self._digest(payload)
        # One day per 200km, minimum one, which is the published rule.
        days = max(1, int((distance + self._KM_PER_DAY - 1) / self._KM_PER_DAY))
        return PortalResult(
            ok=True,
            reference=f"SBX{int(digest[:11], 16)}"[:15],
            valid_until=utc_now().date() + timedelta(days=days),
        )

    def cancel_eway_bill(self, reference: str, *, reason: str) -> PortalResult:
        """Accept a withdrawal."""
        if not reason.strip():
            return PortalResult(
                ok=False,
                error_code="102",
                error_message="A cancellation needs a reason.",
            )
        return PortalResult(ok=True, reference=reference)


def portal_for(mode: str) -> InvoiceRegistrationPortal:
    """Return the portal a firm in this mode talks to.

    LIVE deliberately raises rather than falling back to the sandbox. A firm
    that has switched to LIVE and has no credentials must be told so loudly:
    silently rehearsing while somebody believes they are filing is the worst
    outcome this module has available.
    """
    if mode == "SANDBOX":
        return SandboxPortal()
    raise NotImplementedError(
        "Live registration needs this firm's GSP credentials, which are not "
        "configured. Nothing has been sent. Keep the firm in SANDBOX until "
        "they are, rather than believing a rehearsal was a filing."
    )
