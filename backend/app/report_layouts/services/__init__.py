"""Keep a person's saved layouts of the analysis screens (RPT-1)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError
from app.core.utils.dates import utc_now
from app.report_layouts.models import ReportLayout
from app.report_layouts.schemas import ReportLayoutWrite


class ReportLayoutService:
    """List, save and delete one person's layouts in one firm."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the firm's store session."""
        self._session = session

    def list_layouts(
        self, *, firm_id: UUID, user_id: UUID, report_code: str
    ) -> list[ReportLayout]:
        """Return the person's layouts of one report, by name."""
        return list(
            self._session.scalars(
                select(ReportLayout)
                .where(
                    ReportLayout.firm_id == firm_id,
                    ReportLayout.user_id == user_id,
                    ReportLayout.report_code == report_code,
                    ReportLayout.is_deleted.is_(False),
                )
                .order_by(ReportLayout.name.asc())
            ).all()
        )

    def save(
        self, data: ReportLayoutWrite, *, firm_id: UUID, user_id: UUID
    ) -> ReportLayout:
        """Save under the name, replacing a layout of that name; commit."""
        row = self._session.scalar(
            select(ReportLayout).where(
                ReportLayout.firm_id == firm_id,
                ReportLayout.user_id == user_id,
                ReportLayout.report_code == data.report_code,
                ReportLayout.name == data.name,
                ReportLayout.is_deleted.is_(False),
            )
        )
        action = "report_layout.updated"
        if row is None:
            action = "report_layout.created"
            row = ReportLayout(
                firm_id=firm_id,
                user_id=user_id,
                report_code=data.report_code,
                name=data.name,
                created_by=user_id,
            )
            self._session.add(row)
        row.settings = dict(data.settings)
        row.updated_by = user_id
        self._session.flush()
        record_audit(
            self._session,
            action=action,
            entity_type="report_layout",
            entity_id=row.id,
            actor_id=user_id,
            firm_id=firm_id,
            after_data={"report_code": row.report_code, "name": row.name},
        )
        self._session.commit()
        return row

    def delete(self, layout_id: UUID, *, firm_id: UUID, user_id: UUID) -> None:
        """Delete one of the person's own layouts; commit.

        Raises:
            ResourceNotFoundError: If it is not theirs, or not there.

        """
        row = self._session.get(ReportLayout, layout_id)
        if (
            row is None
            or row.is_deleted
            or row.firm_id != firm_id
            or row.user_id != user_id
        ):
            raise ResourceNotFoundError("Layout not found.")
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.updated_by = user_id
        record_audit(
            self._session,
            action="report_layout.deleted",
            entity_type="report_layout",
            entity_id=row.id,
            actor_id=user_id,
            firm_id=firm_id,
            before_data={"report_code": row.report_code, "name": row.name},
        )
        self._session.commit()


__all__ = ["ReportLayoutService"]
