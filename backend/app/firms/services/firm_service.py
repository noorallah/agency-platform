"""Application service for protected firm management."""

import re
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.concurrency import assert_version
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
        self._assert_storage_unclaimed(storage_payload, current_firm_id=None)
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

    def update(
        self,
        firm_id: UUID,
        data: FirmUpdate,
        actor_id: UUID,
        expected_version: int | None = None,
    ) -> Firm:
        """Replace an existing firm after uniqueness validation."""
        firm = self.get(firm_id)
        assert_version(firm.version, expected_version)
        self._assert_unique(data.code, data.gst_number, data.pan_number, firm.id)
        before = {"name": firm.name, "code": firm.code, "is_active": firm.is_active}
        mapping = self._storage_mapping(firm.id)
        payload, storage_payload = self._normalize_registry_defaults(
            data.model_dump(), mapping
        )
        self._assert_storage_unchanged(mapping, storage_payload)
        self._assert_storage_unclaimed(storage_payload, current_firm_id=firm.id)
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
            after_data={
                "name": firm.name,
                "code": firm.code,
                "is_active": firm.is_active,
            },
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
        before = {"name": firm.name, "code": firm.code, "is_active": firm.is_active}
        firm.is_deleted = True
        firm.deleted_at = utc_now()
        firm.deleted_by = actor_id
        firm.updated_by = actor_id
        # The storage mapping is deliberately left in place: soft deleting a firm
        # does not move the data it already wrote, and FirmRegistryTenantResolver
        # already refuses a deleted firm. Clearing the mapping would make a
        # restored dedicated firm resolve to the shared schema instead.
        record_audit(
            self._session,
            action="firm.deleted",
            entity_type="firm",
            entity_id=firm.id,
            actor_id=actor_id,
            firm_id=firm.id,
            before_data=before,
            after_data={"is_deleted": True},
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
        self,
        payload: dict[str, object],
        existing: FirmStorageMapping | None = None,
    ) -> tuple[dict[str, object], dict[str, object]]:
        # Every tenancy field is optional on the request body, so an update that
        # omits them must inherit what the firm already routes to. Falling back
        # to SHARED instead silently pointed a dedicated firm at the shared
        # schema and orphaned everything it had written.
        raw_mode = payload.get("deployment_mode")
        if raw_mode is None and existing is not None:
            raw_mode = existing.deployment_mode
        mode = (
            DeploymentMode.SHARED if raw_mode is None else DeploymentMode(str(raw_mode))
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
        inherited = (
            existing
            if existing is not None and existing.deployment_mode == mode.value
            else None
        )
        if mode is DeploymentMode.SHARED:
            schema_name: str | None = None
            database_name: str | None = None
        else:
            default_schema = (
                str(payload.get("schema_name") or "").strip()
                or (inherited.schema_name if inherited is not None else None)
                or f"{normalized_dedicated_prefix}{slug}"
            )
            schema_name = _apply_schema_prefix(default_schema, schema_prefix)
            database_name = (
                str(payload.get("database_name") or "").strip()
                or (inherited.database_name if inherited is not None else None)
                or (
                    shared_database_name
                    if mode is DeploymentMode.SCHEMA
                    else f"{dedicated_database_prefix}{slug}"
                )
            )
        storage_payload: dict[str, object] = {
            "deployment_mode": mode.value,
            "database_type": database_type,
            "database_name": database_name,
            "schema_name": schema_name,
            "is_active": True,
        }
        normalized_payload = {
            key: value for key, value in payload.items() if key not in _TENANCY_KEYS
        }
        return normalized_payload, storage_payload

    def _storage_mapping(self, firm_id: UUID) -> FirmStorageMapping | None:
        return self._session.scalar(
            select(FirmStorageMapping).where(FirmStorageMapping.firm_id == firm_id)
        )

    def _assert_storage_unchanged(
        self,
        mapping: FirmStorageMapping | None,
        storage_payload: dict[str, object],
    ) -> None:
        """Refuse a routing change that would strand the firm's existing data.

        Nothing moves a firm's rows between stores, and ``provision_new_firm``
        only runs at creation, so re-pointing a live firm either abandons its
        data or aims it at a schema that was never built.
        """
        if mapping is None:
            return
        current = {
            "deployment_mode": mapping.deployment_mode,
            "database_type": mapping.database_type,
            "database_name": mapping.database_name,
            "schema_name": mapping.schema_name,
        }
        requested = {key: storage_payload[key] for key in current}
        if current != requested:
            raise BusinessRuleError(
                "Firm storage routing cannot be changed after creation "
                f"(currently {current['deployment_mode']}"
                f"/{current['schema_name'] or 'shared'}). Migrate the firm's "
                "data first."
            )

    def _assert_storage_unclaimed(
        self,
        storage_payload: dict[str, object],
        current_firm_id: UUID | None,
    ) -> None:
        """Refuse routing two firms into one store.

        Nothing else stops it: the only uniqueness on ``firm_storage_mappings``
        is one row per firm, so two firms could name the same schema and read
        each other's rows. Soft-deleted firms count — their data is still there.
        """
        schema_name = storage_payload["schema_name"]
        database_name = storage_payload["database_name"]
        if schema_name is None or database_name is None:
            return
        statement = select(FirmStorageMapping.id).where(
            FirmStorageMapping.schema_name == schema_name,
            FirmStorageMapping.database_name == database_name,
            FirmStorageMapping.is_deleted.is_(False),
        )
        if current_firm_id is not None:
            statement = statement.where(FirmStorageMapping.firm_id != current_firm_id)
        if self._session.scalar(statement) is not None:
            raise ConflictError(
                f"Another firm already uses {database_name}/{schema_name}."
            )

    def _upsert_storage_mapping(
        self,
        *,
        firm_id: UUID,
        payload: dict[str, object],
        actor_id: UUID,
    ) -> None:
        mapping = self._storage_mapping(firm_id)
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
