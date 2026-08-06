"""Application service for protected firm management."""

import re
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.config.settings import TenancySettings
from app.core.database.config import DatabaseDialect
from app.core.exceptions import BusinessRuleError, ConflictError, ResourceNotFoundError
from app.core.tenancy import DeploymentMode, TenantStorageLifecycleService
from app.core.utils.dates import utc_now
from app.firms.models import Firm, FirmStorageMapping
from app.firms.schemas import FirmCreate, FirmUpdate
from app.identity.models import UserFirm

_SLUG = re.compile(r"[^a-z0-9]+")


class FirmService:
    """Perform transactional firm CRUD with safe collection querying."""

    def __init__(
        self,
        session: Session,
        storage_lifecycle: TenantStorageLifecycleService | None = None,
        tenancy_settings: TenancySettings | None = None,
    ) -> None:
        """Bind the service to the request unit of work."""
        self._session = session
        self._storage_lifecycle = storage_lifecycle
        self._tenancy_settings = tenancy_settings

    def create(self, data: FirmCreate, actor_id: UUID) -> Firm:
        """Create a uniquely coded firm and audit the mutation."""
        self._assert_unique(data.code, data.gst_number, data.pan_number)
        payload = data.model_dump()
        payload, storage_payload = self._normalize_registry_defaults(payload)
        now = utc_now()
        payload["created_date"] = now
        payload["updated_date"] = now
        firm = Firm(**payload, created_by=actor_id, updated_by=actor_id)
        self._session.add(firm)
        self._session.flush()
        self._upsert_storage_mapping(
            firm_id=firm.id,
            payload=storage_payload,
            actor_id=actor_id,
        )
        self._session.flush()
        if self._storage_lifecycle is not None:
            self._storage_lifecycle.provision_new_firm(firm)
        record_audit(
            self._session,
            action="firm.created",
            entity_type="firm",
            entity_id=firm.id,
            actor_id=actor_id,
            firm_id=firm.id,
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
        payload, storage_payload = self._normalize_registry_defaults(data.model_dump())
        for field, value in payload.items():
            setattr(firm, field, value)
        self._upsert_storage_mapping(
            firm_id=firm.id,
            payload=storage_payload,
            actor_id=actor_id,
        )
        firm.updated_by = actor_id
        firm.updated_date = utc_now()
        record_audit(
            self._session,
            action="firm.updated",
            entity_type="firm",
            entity_id=firm.id,
            actor_id=actor_id,
            firm_id=firm.id,
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
        firm.is_deleted = True
        firm.deleted_at = utc_now()
        firm.deleted_by = actor_id
        firm.updated_by = actor_id
        record_audit(
            self._session,
            action="firm.deleted",
            entity_type="firm",
            entity_id=firm.id,
            actor_id=actor_id,
            firm_id=firm.id,
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

    def _normalize_registry_defaults(
        self, payload: dict[str, object]
    ) -> tuple[dict[str, object], dict[str, object]]:
        raw_mode = payload.get("deployment_mode")
        mode = (
            DeploymentMode.SHARED
            if raw_mode is None
            else DeploymentMode(str(raw_mode))
        )
        code = str(payload["code"])
        slug = _SLUG.sub("_", code.lower()).strip("_") or "firm"
        platform_database_type = (
            self._tenancy_settings.platform_database_type
            if self._tenancy_settings is not None
            else DatabaseDialect.POSTGRESQL
        )
        shared_database_name = (
            self._tenancy_settings.shared_database_name
            if self._tenancy_settings is not None
            else "agency_platform"
        )
        schema_prefix = (
            self._tenancy_settings.schema_prefix
            if self._tenancy_settings is not None
            else ""
        )
        dedicated_schema_prefix = (
            self._tenancy_settings.dedicated_schema_prefix
            if self._tenancy_settings is not None
            else "firm_"
        )
        dedicated_database_prefix = (
            self._tenancy_settings.dedicated_database_prefix
            if self._tenancy_settings is not None
            else "erp_"
        )
        database_type = str(
            payload.get("database_type") or platform_database_type.value
        ).lower()
        if database_type != platform_database_type.value:
            raise BusinessRuleError(
                "Firm database_type must match platform database dialect "
                f"({platform_database_type.value})."
            )
        payload["status"] = str(payload.get("status") or "ACTIVE").upper()
        normalized_dedicated_prefix = _apply_schema_prefix(
            dedicated_schema_prefix, schema_prefix
        )
        if mode is DeploymentMode.SHARED:
            schema_name: str | None = None
            database_name: str | None = None
        else:
            default_schema = str(payload.get("schema_name") or "").strip() or (
                f"{normalized_dedicated_prefix}{slug}"
            )
            schema_name = _apply_schema_prefix(default_schema, schema_prefix)
            database_name = (
                str(payload.get("database_name") or "").strip()
                or (
                    shared_database_name
                    if mode is DeploymentMode.SCHEMA
                    else f"{dedicated_database_prefix}{slug}"
                )
            )
        storage_payload = {
            "deployment_mode": mode.value,
            "database_type": database_type,
            "database_name": database_name,
            "schema_name": schema_name,
            "is_active": True,
        }
        normalized_payload = {
            key: value
            for key, value in payload.items()
            if key not in _TENANCY_KEYS
        }
        return normalized_payload, storage_payload

    def _upsert_storage_mapping(
        self,
        *,
        firm_id: UUID,
        payload: dict[str, object],
        actor_id: UUID,
    ) -> None:
        mapping = self._session.scalar(
            select(FirmStorageMapping).where(FirmStorageMapping.firm_id == firm_id)
        )
        if mapping is None:
            self._session.add(
                FirmStorageMapping(
                    firm_id=firm_id,
                    created_by=actor_id,
                    updated_by=actor_id,
                    **payload,
                )
            )
            return
        for field, value in payload.items():
            setattr(mapping, field, value)
        mapping.is_deleted = False
        mapping.deleted_at = None
        mapping.deleted_by = None
        mapping.updated_by = actor_id


_TENANCY_KEYS = frozenset(
    {"deployment_mode", "database_type", "database_name", "schema_name"}
)


def _apply_schema_prefix(schema_name: str, prefix: str) -> str:
    normalized_prefix = prefix.strip()
    if not normalized_prefix:
        return schema_name
    if schema_name.startswith(normalized_prefix):
        return schema_name
    return f"{normalized_prefix}{schema_name}"
