"""Which route a firm's e-invoices take to the portal (decision A42).

India has no single way: Tally, Marg and Busy register through their own
integration and also export JSON for the portal's bulk upload; Zoho uses its
GSP partner; ERPNext its own credits or the firm's API credentials. So the
route is the firm's choice, one setting, the shape of the messaging providers:

* ``SANDBOX`` -- rehearse; nothing is filed. A firm that never chose is here.
* ``OFFLINE`` -- free and needs no contract: export the invoices as the
  portal's bulk-upload JSON, upload them by hand, import the result.
* ``NIC_DIRECT`` and ``GSP`` -- the live APIs, offered once each is built.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ValidationError
from app.einvoice.models import EInvoiceProvider, EInvoiceSettings

#: The routes a firm may choose today. The live APIs join this set as their
#: adapters are built; choosing one before then would only fail at the first
#: registration.
AVAILABLE_PROVIDERS = (EInvoiceProvider.SANDBOX.value, EInvoiceProvider.OFFLINE.value)


class EInvoiceSettingsService:
    """Read and change the firm's e-invoice route."""

    def __init__(self, session: Session) -> None:
        """Hold the firm's session."""
        self._session = session

    def _stored(self, firm_id: UUID) -> EInvoiceSettings | None:
        """Return the firm's row, or None if it never chose."""
        return self._session.scalar(
            select(EInvoiceSettings).where(
                EInvoiceSettings.firm_id == firm_id,
                EInvoiceSettings.is_deleted.is_(False),
            )
        )

    def provider(self, firm_id: UUID) -> str:
        """Return the firm's route; the sandbox where it never chose."""
        stored = self._stored(firm_id)
        return stored.provider if stored is not None else EInvoiceProvider.SANDBOX.value

    def update(self, firm_id: UUID, provider: str, *, actor_id: UUID) -> str:
        """Change the firm's route, creating its row on the first change.

        Raises:
            ValidationError: For a route not offered yet.

        """
        if provider not in AVAILABLE_PROVIDERS:
            raise ValidationError(
                f"{provider} is not available yet; choose one of "
                f"{', '.join(AVAILABLE_PROVIDERS)}."
            )
        row = self._stored(firm_id)
        before = None if row is None else row.provider
        if row is None:
            row = EInvoiceSettings(firm_id=firm_id, created_by=actor_id)
            self._session.add(row)
        row.provider = provider
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="einvoice_settings.updated",
            entity_type="einvoice_settings",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=None if before is None else {"provider": before},
            after_data={"provider": provider},
        )
        self._session.commit()
        return provider
