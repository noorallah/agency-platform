"""Application service for recording and reading error reports."""

import hashlib
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.utils.dates import utc_now
from app.diagnostics.models import ErrorReport
from app.diagnostics.schemas import ClientErrorReportCreate

SOURCE_CLIENT = "CLIENT"
SOURCE_SERVER = "SERVER"


#: Path fragments that mark a frame as this codebase rather than a library.
_APPLICATION_MARKERS = ("\\app\\", "/app/")

#: How many frames make up a fault's identity.
_FRAME_DEPTH = 5


def _identifying_frames(stack_trace: str | None) -> list[str]:
    """Return the frames that say *where* a fault happened.

    The frames nearest the raise, and this codebase's own, because neither end
    of a Python traceback identifies anything on its own. The first five lines
    are always the ASGI plumbing -- ``starlette/middleware/errors.py`` and its
    neighbours -- and the last are usually the library that raised, pydantic
    more often than not.

    Hashing the first five was the original rule, and it collapsed every server
    fault of one exception type into a single group: measured on this
    deployment, 28 ``ValidationError``s from **four** different endpoints shared
    one fingerprint, and the triage screen showed whichever context_label came
    first. A triager would have fixed one endpoint and believed the fault gone.

    Line numbers and the argument list go: they move with every edit, and would
    hand one fault a new identity on each release.
    """
    frames = [
        line.strip()
        for line in (stack_trace or "").splitlines()
        if line.strip().startswith("File ")
    ]
    application = [
        frame
        for frame in frames
        if any(marker in frame for marker in _APPLICATION_MARKERS)
    ]
    # A fault entirely inside a library still has to group somehow.
    chosen = (application or frames)[-_FRAME_DEPTH:]
    if not chosen:
        # A client report, or a trace in a shape we do not recognise: fall back
        # to the leading lines, which is where a Dart stack puts the throw site.
        chosen = [
            line.strip() for line in (stack_trace or "").splitlines() if line.strip()
        ][:_FRAME_DEPTH]
    return [frame.split(", line ")[0].split("(")[0].strip() for frame in chosen]


def fingerprint_for(error_type: str, stack_trace: str | None) -> str:
    """Return a stable identity for "the same fault"."""
    material = f"{error_type}|{'|'.join(_identifying_frames(stack_trace))}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


class ErrorReportService:
    """Record failures and answer triage questions about them."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the platform unit of work."""
        self._session = session

    def record_client_report(
        self,
        data: ClientErrorReportCreate,
        *,
        firm_id: UUID | None,
        user_id: UUID | None,
    ) -> ErrorReport:
        """Store one report sent by a desktop client."""
        report = ErrorReport(
            source=SOURCE_CLIENT,
            fingerprint=data.fingerprint,
            error_type=data.error_type,
            message=data.message,
            stack_trace=data.stack_trace,
            app_version=data.app_version,
            build_number=data.build_number,
            platform_info=data.platform_info,
            firm_id=firm_id,
            user_id=user_id,
            request_id=data.request_id,
            context_label=data.context_label,
            breadcrumbs=data.breadcrumbs or None,
            occurred_at=data.occurred_at,
            received_at=utc_now(),
        )
        self._session.add(report)
        self._session.commit()
        return report

    def record_server_error(
        self,
        *,
        error_type: str,
        message: str,
        stack_trace: str | None,
        request_id: str | None,
        context_label: str | None = None,
    ) -> None:
        """Store one unhandled server failure.

        Swallows its own failures on purpose. This runs while the request is
        already failing; a diagnostics write that raised would replace a useful
        500 with a confusing one.
        """
        try:
            self._session.add(
                ErrorReport(
                    source=SOURCE_SERVER,
                    fingerprint=fingerprint_for(error_type, stack_trace),
                    error_type=error_type[:200],
                    message=message[:8000],
                    stack_trace=(stack_trace or None) and stack_trace[:20000],
                    request_id=request_id,
                    context_label=context_label,
                    received_at=utc_now(),
                )
            )
            self._session.commit()
        except Exception:  # noqa: BLE001 - diagnostics must never mask the fault
            self._session.rollback()

    def list_groups(
        self,
        page: int,
        page_size: int,
        search: str | None = None,
        source: str | None = None,
    ) -> tuple[list[dict[str, object]], int]:
        """Return faults collapsed by fingerprint, most recent first."""
        grouped = (
            select(
                ErrorReport.fingerprint,
                func.min(ErrorReport.source).label("source"),
                func.min(ErrorReport.error_type).label("error_type"),
                func.min(ErrorReport.message).label("message"),
                func.count(ErrorReport.id).label("occurrences"),
                func.min(ErrorReport.received_at).label("first_seen"),
                func.max(ErrorReport.received_at).label("last_seen"),
            )
            .group_by(ErrorReport.fingerprint)
            .order_by(func.max(ErrorReport.received_at).desc())
        )
        if source is not None:
            grouped = grouped.where(ErrorReport.source == source.upper())
        if search:
            pattern = f"%{search.lower()}%"
            grouped = grouped.where(
                func.lower(ErrorReport.message).like(pattern)
                | func.lower(ErrorReport.error_type).like(pattern)
            )
        subquery = grouped.subquery()
        total = self._session.scalar(select(func.count()).select_from(subquery)) or 0
        rows = self._session.execute(
            grouped.offset((page - 1) * page_size).limit(page_size)
        ).all()
        groups: list[dict[str, object]] = []
        for row in rows:
            versions = (
                self._session.scalars(
                    select(ErrorReport.app_version)
                    .where(
                        ErrorReport.fingerprint == row.fingerprint,
                        ErrorReport.app_version.is_not(None),
                    )
                    .distinct()
                    .limit(10)
                ).all()
                or []
            )
            groups.append(
                {
                    "fingerprint": row.fingerprint,
                    "source": row.source,
                    "error_type": row.error_type,
                    "message": row.message,
                    "occurrences": row.occurrences,
                    "first_seen": row.first_seen,
                    "last_seen": row.last_seen,
                    "app_versions": [version for version in versions if version],
                }
            )
        return groups, total

    def list_occurrences(self, fingerprint: str, limit: int = 50) -> list[ErrorReport]:
        """Return individual occurrences of one fault, newest first."""
        return list(
            self._session.scalars(
                select(ErrorReport)
                .where(ErrorReport.fingerprint == fingerprint)
                .order_by(ErrorReport.received_at.desc())
                .limit(limit)
            ).all()
        )

    def purge_before(self, cutoff: datetime) -> int:
        """Delete reports received before ``cutoff``; returns the count removed."""
        rows = list(
            self._session.scalars(
                select(ErrorReport).where(ErrorReport.received_at < cutoff)
            ).all()
        )
        for row in rows:
            self._session.delete(row)
        self._session.commit()
        return len(rows)
