"""Application service for protected firm management."""

from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import BusinessRuleError, ConflictError, ResourceNotFoundError
from app.core.utils.dates import utc_now
from app.firms.models import Firm
from app.firms.schemas import FirmCreate, FirmUpdate
from app.identity.models import UserFirm


class FirmService:
    """Perform transactional firm CRUD with safe collection querying."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session

    def create(self, data: FirmCreate, actor_id: UUID) -> Firm:
        """Create a uniquely coded firm and audit the mutation."""
        self._assert_unique(data.code, data.gst_number, data.pan_number)
        firm = Firm(**data.model_dump(), created_by=actor_id, updated_by=actor_id)
        self._session.add(firm)
        self._session.flush()
        record_audit(
            self._session,
            action="firm.created",
            entity_type="firm",
            entity_id=firm.id,
            actor_id=actor_id,
            after_data={"code": firm.code},
        )
        self._session.commit()
        return firm

    def get(self, firm_id: UUID) -> Firm:
        """Return one visible firm."""
        firm = self._session.scalar(
            select(Firm).where(Firm.id == firm_id, Firm.is_deleted.is_(False))
        )
        if firm is None:
            raise ResourceNotFoundError("Firm not found.")
        return firm

    def update(self, firm_id: UUID, data: FirmUpdate, actor_id: UUID) -> Firm:
        """Replace an existing firm after uniqueness validation."""
        firm = self.get(firm_id)
        self._assert_unique(data.code, data.gst_number, data.pan_number, firm.id)
        before = {"name": firm.name, "code": firm.code, "is_active": firm.is_active}
        for field, value in data.model_dump().items():
            setattr(firm, field, value)
        firm.updated_by = actor_id
        record_audit(
            self._session,
            action="firm.updated",
            entity_type="firm",
            entity_id=firm.id,
            actor_id=actor_id,
            before_data=before,
        )
        self._session.commit()
        return firm

    def delete(self, firm_id: UUID, actor_id: UUID) -> None:
        """Soft delete an unassigned firm."""
        firm = self.get(firm_id)
        if (
            self._session.scalar(
                select(UserFirm.id).where(
                    UserFirm.firm_id == firm.id, UserFirm.is_deleted.is_(False)
                )
            )
            is not None
        ):
            raise BusinessRuleError("Assigned firms cannot be deleted.")
        firm.is_deleted, firm.deleted_at, firm.updated_by = True, utc_now(), actor_id
        record_audit(
            self._session,
            action="firm.deleted",
            entity_type="firm",
            entity_id=firm.id,
            actor_id=actor_id,
        )
        self._session.commit()

    def list(
        self,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[Firm], int]:
        """Return a paginated firm page using only approved sorting fields."""
        columns = {"name": Firm.name, "code": Firm.code, "created_at": Firm.created_at}
        statement = select(Firm).where(Firm.is_deleted.is_(False))
        count = select(func.count()).select_from(Firm).where(Firm.is_deleted.is_(False))
        if search:
            condition = or_(
                Firm.name.ilike(f"%{search.strip()}%"),
                Firm.code.ilike(f"%{search.strip()}%"),
            )
            statement, count = statement.where(condition), count.where(condition)
        ordering = columns[sort_by].desc() if descending else columns[sort_by].asc()
        rows = self._session.scalars(
            statement.order_by(ordering).offset((page - 1) * page_size).limit(page_size)
        ).all()
        return list(rows), int(self._session.scalar(count) or 0)

    def _assert_unique(
        self,
        code: str,
        gst_number: str | None,
        pan_number: str | None,
        current_id: UUID | None = None,
    ) -> None:
        conditions = [Firm.code == code]
        if gst_number:
            conditions.append(Firm.gst_number == gst_number)
        if pan_number:
            conditions.append(Firm.pan_number == pan_number)
        statement = select(Firm.id).where(Firm.is_deleted.is_(False), or_(*conditions))
        if current_id:
            statement = statement.where(Firm.id != current_id)
        if self._session.scalar(statement) is not None:
            raise ConflictError("Firm code, GST number, or PAN number already exists.")
