"""The transporter master (backlog §87 #5, SG-5).

A firm ships with the same few carriers every day, and the delivery note used
to have each one's name and GSTIN typed afresh. This keeps them once -- name,
GSTIN or TRANSIN, phone, usual mode -- and the note picks one, as Tally, Busy
and Marg do. The note still owns its transport columns: choosing a carrier
fills them, and they are what the challan prints and the e-way bill reads.
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ConflictError, ResourceNotFoundError
from app.core.utils.dates import utc_now
from app.core.validation.common import normalize_gstin
from app.delivery_note.models.transporter import Transporter


class TransporterWrite(BaseModel):
    """Create or change one transporter."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    gstin: str | None = Field(default=None, max_length=20)
    transporter_ref: str | None = Field(default=None, max_length=20)
    phone: str | None = Field(default=None, max_length=30)
    default_mode: Literal["ROAD", "RAIL", "AIR", "SHIP"] | None = None
    is_active: bool = True

    @field_validator("name", mode="before")
    @classmethod
    def _trim_name(cls, value: str) -> str:
        """Drop the spaces around a name."""
        return value.strip() if isinstance(value, str) else value

    @field_validator("gstin", "transporter_ref", mode="before")
    @classmethod
    def _normalize_id(cls, value: str | None) -> str | None:
        """Refuse an id that is not the shape of a GSTIN; a blank is none."""
        return normalize_gstin(value)

    @field_validator("phone", mode="before")
    @classmethod
    def _blank_phone(cls, value: str | None) -> str | None:
        """Store a blank phone as none."""
        return (value or "").strip() or None


class TransporterResponse(BaseModel):
    """One transporter."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    name: str
    gstin: str | None
    transporter_ref: str | None
    phone: str | None
    default_mode: str | None
    is_active: bool
    version: int


class TransporterService:
    """Keep the firm's transporters."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request's session."""
        self._session = session

    def transporters(
        self, firm_id: UUID, *, active_only: bool = False
    ) -> list[TransporterResponse]:
        """Return the firm's transporters by name."""
        statement = select(Transporter).where(
            Transporter.firm_id == firm_id, Transporter.is_deleted.is_(False)
        )
        if active_only:
            statement = statement.where(Transporter.is_active.is_(True))
        return [
            TransporterResponse.model_validate(row)
            for row in self._session.scalars(
                statement.order_by(Transporter.name.asc())
            ).all()
        ]

    def get(self, transporter_id: UUID, firm_id: UUID) -> Transporter:
        """Return one live transporter of the firm.

        Raises:
            ResourceNotFoundError: If the firm has no such transporter.

        """
        row = self._session.scalar(
            select(Transporter).where(
                Transporter.id == transporter_id,
                Transporter.firm_id == firm_id,
                Transporter.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Transporter not found.")
        return row

    def save(
        self,
        data: TransporterWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
        transporter_id: UUID | None = None,
    ) -> TransporterResponse:
        """Create a transporter, or change one; commit.

        Raises:
            ConflictError: If another live transporter has the name.

        """
        # Kept once by name whatever its capitals or the spaces around it:
        # "Blue Dart" and "blue dart" were two carriers (D-SELL-68).
        clash = self._session.execute(
            select(Transporter.id, Transporter.name).where(
                Transporter.firm_id == firm_id,
                func.lower(func.trim(Transporter.name)) == data.name.strip().lower(),
                Transporter.is_deleted.is_(False),
                *(
                    ()
                    if transporter_id is None
                    else (Transporter.id != transporter_id,)
                ),
            )
        ).first()
        if clash is not None:
            raise ConflictError(f"There is already a transporter {clash.name}.")
        if transporter_id is None:
            row = Transporter(firm_id=firm_id, created_by=actor_id, **data.model_dump())
            self._session.add(row)
        else:
            row = self.get(transporter_id, firm_id)
            for field, value in data.model_dump().items():
                setattr(row, field, value)
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="transporter.saved",
            entity_type="transporter",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"name": row.name},
        )
        self._session.commit()
        return TransporterResponse.model_validate(row)

    def delete(self, transporter_id: UUID, *, firm_id: UUID, actor_id: UUID) -> None:
        """Remove a transporter; commit.

        The notes that named it keep the name and id they copied, so nothing
        stands in the way of removing one the firm no longer uses.
        """
        row = self.get(transporter_id, firm_id)
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="transporter.deleted",
            entity_type="transporter",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={"name": row.name},
        )
        self._session.commit()


__all__ = [
    "TransporterResponse",
    "TransporterService",
    "TransporterWrite",
]
