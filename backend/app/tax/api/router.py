"""Firm-scoped REST endpoints for enterprise tax framework."""

import csv
from io import StringIO
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database.dependencies import get_db, get_platform_db
from app.core.exceptions import AuthorizationError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.core.security.authorization import (
    Principal,
    get_current_principal,
    require_permission,
)
from app.firms.models import Firm
from app.identity.models import UserFirm
from app.tax.schemas import (
    BulkTaxStatusRequest,
    BulkUuidRequest,
    EffectiveDateRecord,
    TaxComponentResponse,
    TaxComponentWrite,
    TaxCountryMappingResponse,
    TaxCountryMappingWrite,
    TaxHistoryRecord,
    TaxRuleConditionResponse,
    TaxRuleExecutionLogResponse,
    TaxRuleImportRequest,
    TaxRulePriorityRecord,
    TaxRuleResponse,
    TaxRuleSimulationRequest,
    TaxRuleSimulationResponse,
    TaxRuleWrite,
    TaxImportSystemsRequest,
    TaxMigrationMappingResponse,
    TaxMigrationMappingWrite,
    TaxProfileResponse,
    TaxProfileWrite,
    TaxSettingsResponse,
    TaxSettingsWrite,
    TaxSetupResponse,
    TaxSetupWrite,
    TaxStatus,
    TaxSystemResponse,
    TaxSystemWrite,
)
from app.tax.services import TaxFrameworkService, TaxRuleService

router = APIRouter(
    prefix="/api/v1/tax-framework",
    tags=["Enterprise Tax Framework"],
    responses=STANDARD_ERROR_RESPONSES,
)


class TaxScope:
    """Carry authenticated principal and resolved firm context."""

    def __init__(self, principal: Principal, firm_id: UUID) -> None:
        self.principal = principal
        self.firm_id = firm_id

    @property
    def actor_id(self) -> UUID:
        if not isinstance(self.principal.subject, UUID):
            raise RuntimeError("Tax framework management requires a user principal.")
        return self.principal.subject


def tax_scope(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_platform_db)],
    x_firm_id: Annotated[UUID | None, Header(alias="X-Firm-ID")] = None,
) -> TaxScope:
    if "platform_admin" in principal.roles:
        if x_firm_id is None:
            raise AuthorizationError("X-Firm-ID is required for firm-owned resources.")
        firm = db.scalar(
            select(Firm.id).where(
                Firm.id == x_firm_id,
                Firm.is_active.is_(True),
                Firm.is_deleted.is_(False),
            )
        )
        if firm is None:
            raise AuthorizationError("The selected firm is inactive or unavailable.")
        return TaxScope(principal, x_firm_id)
    if not isinstance(principal.subject, UUID) or x_firm_id is None:
        raise AuthorizationError("An authorized active firm is required.")
    membership = db.scalar(
        select(UserFirm.id)
        .join(Firm, Firm.id == UserFirm.firm_id)
        .where(
            UserFirm.user_id == principal.subject,
            UserFirm.firm_id == x_firm_id,
            UserFirm.is_active.is_(True),
            UserFirm.is_deleted.is_(False),
            Firm.is_active.is_(True),
            Firm.is_deleted.is_(False),
        )
    )
    if membership is None:
        raise AuthorizationError("You are not authorized for the selected firm.")
    return TaxScope(principal, x_firm_id)


def _permission(code: str) -> object:
    def dependency(
        _: Annotated[Principal, Depends(require_permission(code))],
        scope: Annotated[TaxScope, Depends(tax_scope)],
    ) -> TaxScope:
        return scope

    return Depends(dependency)


TaxViewScope = Annotated[TaxScope, _permission("TAX_VIEW")]
TaxCreateScope = Annotated[TaxScope, _permission("TAX_CREATE")]
TaxUpdateScope = Annotated[TaxScope, _permission("TAX_UPDATE")]
TaxDeleteScope = Annotated[TaxScope, _permission("TAX_DELETE")]
TaxRestoreScope = Annotated[TaxScope, _permission("TAX_RESTORE")]
TaxImportScope = Annotated[TaxScope, _permission("TAX_IMPORT")]
TaxExportScope = Annotated[TaxScope, _permission("TAX_EXPORT")]
TaxSettingsScope = Annotated[TaxScope, _permission("TAX_MANAGE_SETTINGS")]
TaxRuleViewScope = Annotated[TaxScope, _permission("TAX_RULE_VIEW")]
TaxRuleCreateScope = Annotated[TaxScope, _permission("TAX_RULE_CREATE")]
TaxRuleUpdateScope = Annotated[TaxScope, _permission("TAX_RULE_UPDATE")]
TaxRuleDeleteScope = Annotated[TaxScope, _permission("TAX_RULE_DELETE")]
TaxRuleRestoreScope = Annotated[TaxScope, _permission("TAX_RULE_RESTORE")]
TaxRuleSimulateScope = Annotated[TaxScope, _permission("TAX_SIMULATE")]


@router.get("/systems", response_model=PaginatedResponse[TaxSystemResponse])
def list_tax_systems(
    scope: TaxViewScope,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    country_id: UUID | None = None,
    business_profile_id: UUID | None = None,
    status: TaxStatus | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> PaginatedResponse[TaxSystemResponse]:
    params = PaginationParams(page=page, page_size=page_size)
    rows, total = TaxFrameworkService(db).list_systems(
        firm_scope=scope.firm_id,
        page=params.page,
        page_size=params.page_size,
        search=search,
        country_id=country_id,
        business_profile_id=business_profile_id,
        status=status,
        include_deleted=include_deleted,
    )
    return PaginatedResponse(
        data=[TaxSystemResponse.model_validate(row) for row in rows],
        pagination=params.metadata(total),
    )


@router.post(
    "/systems",
    response_model=ApiResponse[TaxSystemResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_tax_system(
    data: TaxSystemWrite,
    scope: TaxCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TaxSystemResponse]:
    row = TaxFrameworkService(db).create_system(
        data,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=TaxSystemResponse.model_validate(row))


@router.put("/systems/{system_id}", response_model=ApiResponse[TaxSystemResponse])
def update_tax_system(
    system_id: UUID,
    data: TaxSystemWrite,
    scope: TaxUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TaxSystemResponse]:
    row = TaxFrameworkService(db).update_system(
        system_id,
        data,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=TaxSystemResponse.model_validate(row))


@router.delete("/systems/{system_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tax_system(
    system_id: UUID,
    scope: TaxDeleteScope,
    db: Session = Depends(get_db),
) -> Response:
    TaxFrameworkService(db).delete_system(
        system_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/systems/{system_id}/restore", response_model=ApiResponse[TaxSystemResponse])
def restore_tax_system(
    system_id: UUID,
    scope: TaxRestoreScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TaxSystemResponse]:
    row = TaxFrameworkService(db).restore_system(
        system_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=TaxSystemResponse.model_validate(row))


@router.post("/systems/bulk-delete", response_model=ApiResponse[dict[str, int]])
def bulk_delete_systems(
    data: BulkUuidRequest,
    scope: TaxDeleteScope,
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, int]]:
    affected = TaxFrameworkService(db).bulk_delete_systems(
        data.ids,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data={"affected": affected})


@router.post("/systems/bulk-restore", response_model=ApiResponse[dict[str, int]])
def bulk_restore_systems(
    data: BulkUuidRequest,
    scope: TaxRestoreScope,
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, int]]:
    affected = TaxFrameworkService(db).bulk_restore_systems(
        data.ids,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data={"affected": affected})


@router.get("/systems/export")
def export_tax_systems(
    scope: TaxExportScope,
    search: str | None = None,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    text = TaxFrameworkService(db).export_systems_csv(
        firm_scope=scope.firm_id,
        search=search,
    )
    return StreamingResponse(
        iter([text]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="tax_systems.csv"'},
    )


@router.post(
    "/systems/import",
    response_model=ApiResponse[list[TaxSystemResponse]],
    status_code=status.HTTP_201_CREATED,
)
def import_tax_systems(
    data: TaxImportSystemsRequest,
    scope: TaxImportScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[TaxSystemResponse]]:
    rows = TaxFrameworkService(db).import_systems(
        data.systems,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=[TaxSystemResponse.model_validate(row) for row in rows])


# ─── Composite Setup Endpoints ────────────────────────────────────────────────

@router.post(
    "/setup",
    response_model=ApiResponse[TaxSetupResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create full tax setup in one call",
    description=(
        "Creates a tax system, all its components, and all profiles with their "
        "component assignments in a single atomic transaction. "
        "Profile components are referenced by component code (not ID)."
    ),
)
def create_tax_setup(
    data: TaxSetupWrite,
    scope: TaxCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TaxSetupResponse]:
    system, components, profiles = TaxFrameworkService(db).create_setup(
        data,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(
        data=TaxSetupResponse(
            system=TaxSystemResponse.model_validate(system),
            components=[TaxComponentResponse.model_validate(c) for c in components],
            profiles=[TaxProfileResponse.model_validate(p) for p in profiles],
        )
    )


@router.put(
    "/setup/{system_id}",
    response_model=ApiResponse[TaxSetupResponse],
    summary="Update full tax setup in one call",
    description=(
        "Updates a tax system, upserts components and profiles. "
        "Supply 'id' on components/profiles to update existing ones; "
        "omit 'id' to create new ones. "
        "Existing items not mentioned are left untouched."
    ),
)
def update_tax_setup(
    system_id: UUID,
    data: TaxSetupWrite,
    scope: TaxUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TaxSetupResponse]:
    system, components, profiles = TaxFrameworkService(db).update_setup(
        system_id,
        data,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(
        data=TaxSetupResponse(
            system=TaxSystemResponse.model_validate(system),
            components=[TaxComponentResponse.model_validate(c) for c in components],
            profiles=[TaxProfileResponse.model_validate(p) for p in profiles],
        )
    )


@router.get(
    "/setup/{system_id}",
    response_model=ApiResponse[TaxSetupResponse],
    summary="Get full tax setup for a system",
    description="Returns the tax system plus all its components and profiles.",
)
def get_tax_setup(
    system_id: UUID,
    scope: TaxViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TaxSetupResponse]:
    system, components, profiles = TaxFrameworkService(db).get_setup(
        system_id,
        firm_scope=scope.firm_id,
    )
    return ApiResponse(
        data=TaxSetupResponse(
            system=TaxSystemResponse.model_validate(system),
            components=[TaxComponentResponse.model_validate(c) for c in components],
            profiles=[TaxProfileResponse.model_validate(p) for p in profiles],
        )
    )


@router.get("/components", response_model=PaginatedResponse[TaxComponentResponse])
def list_tax_components(
    scope: TaxViewScope,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    tax_system_id: UUID | None = None,
    status: TaxStatus | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> PaginatedResponse[TaxComponentResponse]:
    params = PaginationParams(page=page, page_size=page_size)
    rows, total = TaxFrameworkService(db).list_components(
        firm_scope=scope.firm_id,
        page=params.page,
        page_size=params.page_size,
        search=search,
        tax_system_id=tax_system_id,
        status=status,
        include_deleted=include_deleted,
    )
    return PaginatedResponse(
        data=[TaxComponentResponse.model_validate(row) for row in rows],
        pagination=params.metadata(total),
    )


@router.post(
    "/components",
    response_model=ApiResponse[TaxComponentResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_tax_component(
    data: TaxComponentWrite,
    scope: TaxCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TaxComponentResponse]:
    row = TaxFrameworkService(db).create_component(
        data,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=TaxComponentResponse.model_validate(row))


@router.put("/components/{component_id}", response_model=ApiResponse[TaxComponentResponse])
def update_tax_component(
    component_id: UUID,
    data: TaxComponentWrite,
    scope: TaxUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TaxComponentResponse]:
    row = TaxFrameworkService(db).update_component(
        component_id,
        data,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=TaxComponentResponse.model_validate(row))


@router.delete("/components/{component_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tax_component(
    component_id: UUID,
    scope: TaxDeleteScope,
    db: Session = Depends(get_db),
) -> Response:
    TaxFrameworkService(db).delete_component(
        component_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/components/{component_id}/restore",
    response_model=ApiResponse[TaxComponentResponse],
)
def restore_tax_component(
    component_id: UUID,
    scope: TaxRestoreScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TaxComponentResponse]:
    row = TaxFrameworkService(db).restore_component(
        component_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=TaxComponentResponse.model_validate(row))


@router.post("/components/bulk-delete", response_model=ApiResponse[dict[str, int]])
def bulk_delete_components(
    data: BulkUuidRequest,
    scope: TaxDeleteScope,
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, int]]:
    affected = TaxFrameworkService(db).bulk_delete_components(
        data.ids,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data={"affected": affected})


@router.post("/components/bulk-restore", response_model=ApiResponse[dict[str, int]])
def bulk_restore_components(
    data: BulkUuidRequest,
    scope: TaxRestoreScope,
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, int]]:
    affected = TaxFrameworkService(db).bulk_restore_components(
        data.ids,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data={"affected": affected})


@router.get("/profiles", response_model=PaginatedResponse[TaxProfileResponse])
def list_tax_profiles(
    scope: TaxViewScope,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    tax_system_id: UUID | None = None,
    business_profile_id: UUID | None = None,
    status: TaxStatus | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> PaginatedResponse[TaxProfileResponse]:
    params = PaginationParams(page=page, page_size=page_size)
    rows, total = TaxFrameworkService(db).list_profiles(
        firm_scope=scope.firm_id,
        page=params.page,
        page_size=params.page_size,
        search=search,
        tax_system_id=tax_system_id,
        business_profile_id=business_profile_id,
        status=status,
        include_deleted=include_deleted,
    )
    return PaginatedResponse(
        data=[TaxProfileResponse.model_validate(row) for row in rows],
        pagination=params.metadata(total),
    )


@router.post(
    "/profiles",
    response_model=ApiResponse[TaxProfileResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_tax_profile(
    data: TaxProfileWrite,
    scope: TaxCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TaxProfileResponse]:
    row = TaxFrameworkService(db).create_profile(
        data,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=TaxProfileResponse.model_validate(row))


@router.put("/profiles/{profile_id}", response_model=ApiResponse[TaxProfileResponse])
def update_tax_profile(
    profile_id: UUID,
    data: TaxProfileWrite,
    scope: TaxUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TaxProfileResponse]:
    row = TaxFrameworkService(db).update_profile(
        profile_id,
        data,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=TaxProfileResponse.model_validate(row))


@router.delete("/profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tax_profile(
    profile_id: UUID,
    scope: TaxDeleteScope,
    db: Session = Depends(get_db),
) -> Response:
    TaxFrameworkService(db).delete_profile(
        profile_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/profiles/{profile_id}/restore", response_model=ApiResponse[TaxProfileResponse])
def restore_tax_profile(
    profile_id: UUID,
    scope: TaxRestoreScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TaxProfileResponse]:
    row = TaxFrameworkService(db).restore_profile(
        profile_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=TaxProfileResponse.model_validate(row))


@router.post("/profiles/bulk-delete", response_model=ApiResponse[dict[str, int]])
def bulk_delete_profiles(
    data: BulkUuidRequest,
    scope: TaxDeleteScope,
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, int]]:
    affected = TaxFrameworkService(db).bulk_delete_profiles(
        data.ids,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data={"affected": affected})


@router.post("/profiles/bulk-restore", response_model=ApiResponse[dict[str, int]])
def bulk_restore_profiles(
    data: BulkUuidRequest,
    scope: TaxRestoreScope,
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, int]]:
    affected = TaxFrameworkService(db).bulk_restore_profiles(
        data.ids,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data={"affected": affected})


@router.post("/profiles/bulk-status", response_model=ApiResponse[dict[str, int]])
def bulk_profile_status(
    data: BulkTaxStatusRequest,
    scope: TaxUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, int]]:
    affected = TaxFrameworkService(db).bulk_profile_status(
        data.ids,
        data.status,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data={"affected": affected})


@router.get("/country-mappings", response_model=ApiResponse[list[TaxCountryMappingResponse]])
def list_country_mappings(
    scope: TaxViewScope,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[list[TaxCountryMappingResponse]]:
    rows = TaxFrameworkService(db).list_country_mappings(
        firm_scope=scope.firm_id,
        include_deleted=include_deleted,
    )
    return ApiResponse(data=[TaxCountryMappingResponse.model_validate(row) for row in rows])


@router.post(
    "/country-mappings",
    response_model=ApiResponse[TaxCountryMappingResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_country_mapping(
    data: TaxCountryMappingWrite,
    scope: TaxCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TaxCountryMappingResponse]:
    row = TaxFrameworkService(db).create_country_mapping(
        data,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=TaxCountryMappingResponse.model_validate(row))


@router.put(
    "/country-mappings/{mapping_id}",
    response_model=ApiResponse[TaxCountryMappingResponse],
)
def update_country_mapping(
    mapping_id: UUID,
    data: TaxCountryMappingWrite,
    scope: TaxUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TaxCountryMappingResponse]:
    row = TaxFrameworkService(db).update_country_mapping(
        mapping_id,
        data,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=TaxCountryMappingResponse.model_validate(row))


@router.delete("/country-mappings/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_country_mapping(
    mapping_id: UUID,
    scope: TaxDeleteScope,
    db: Session = Depends(get_db),
) -> Response:
    TaxFrameworkService(db).delete_country_mapping(
        mapping_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/migration-mappings",
    response_model=ApiResponse[list[TaxMigrationMappingResponse]],
)
def list_migration_mappings(
    scope: TaxViewScope,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[list[TaxMigrationMappingResponse]]:
    rows = TaxFrameworkService(db).list_migration_mappings(
        firm_scope=scope.firm_id,
        include_deleted=include_deleted,
    )
    return ApiResponse(
        data=[TaxMigrationMappingResponse.model_validate(row) for row in rows]
    )


@router.post(
    "/migration-mappings",
    response_model=ApiResponse[TaxMigrationMappingResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_migration_mapping(
    data: TaxMigrationMappingWrite,
    scope: TaxCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TaxMigrationMappingResponse]:
    row = TaxFrameworkService(db).create_migration_mapping(
        data,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=TaxMigrationMappingResponse.model_validate(row))


@router.put(
    "/migration-mappings/{mapping_id}",
    response_model=ApiResponse[TaxMigrationMappingResponse],
)
def update_migration_mapping(
    mapping_id: UUID,
    data: TaxMigrationMappingWrite,
    scope: TaxUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TaxMigrationMappingResponse]:
    row = TaxFrameworkService(db).update_migration_mapping(
        mapping_id,
        data,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=TaxMigrationMappingResponse.model_validate(row))


@router.delete("/migration-mappings/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_migration_mapping(
    mapping_id: UUID,
    scope: TaxDeleteScope,
    db: Session = Depends(get_db),
) -> Response:
    TaxFrameworkService(db).delete_migration_mapping(
        mapping_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/effective-dates", response_model=ApiResponse[list[EffectiveDateRecord]])
def effective_dates(
    scope: TaxViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[EffectiveDateRecord]]:
    rows = TaxFrameworkService(db).effective_dates(firm_scope=scope.firm_id)
    return ApiResponse(data=rows)


@router.get("/settings", response_model=ApiResponse[TaxSettingsResponse])
def get_tax_settings(
    scope: TaxViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TaxSettingsResponse]:
    row = TaxFrameworkService(db).get_settings(firm_scope=scope.firm_id)
    return ApiResponse(data=TaxSettingsResponse.model_validate(row))


@router.put("/settings", response_model=ApiResponse[TaxSettingsResponse])
def update_tax_settings(
    data: TaxSettingsWrite,
    scope: TaxSettingsScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TaxSettingsResponse]:
    row = TaxFrameworkService(db).update_settings(
        data,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=TaxSettingsResponse.model_validate(row))


@router.get("/history", response_model=ApiResponse[list[TaxHistoryRecord]])
def tax_history(
    scope: TaxViewScope,
    limit: int = Query(default=200, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> ApiResponse[list[TaxHistoryRecord]]:
    rows = TaxFrameworkService(db).history(firm_scope=scope.firm_id, limit=limit)
    return ApiResponse(data=rows)


@router.get("/rules", response_model=PaginatedResponse[TaxRuleResponse])
def list_tax_rules(
    scope: TaxRuleViewScope,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    country_id: UUID | None = None,
    business_profile_id: UUID | None = None,
    tax_profile_id: UUID | None = None,
    transaction_type: str | None = None,
    status: TaxStatus | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> PaginatedResponse[TaxRuleResponse]:
    params = PaginationParams(page=page, page_size=page_size)
    rows, total = TaxRuleService(db).list_rules(
        firm_scope=scope.firm_id,
        page=params.page,
        page_size=params.page_size,
        search=search,
        country_id=country_id,
        business_profile_id=business_profile_id,
        tax_profile_id=tax_profile_id,
        transaction_type=transaction_type,
        status=status,
        include_deleted=include_deleted,
    )
    return PaginatedResponse(
        data=[TaxRuleResponse.model_validate(row) for row in rows],
        pagination=params.metadata(total),
    )


@router.post(
    "/rules",
    response_model=ApiResponse[TaxRuleResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_tax_rule(
    data: TaxRuleWrite,
    scope: TaxRuleCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TaxRuleResponse]:
    row = TaxRuleService(db).create_rule(
        data,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=TaxRuleResponse.model_validate(row))


@router.put("/rules/{rule_id}", response_model=ApiResponse[TaxRuleResponse])
def update_tax_rule(
    rule_id: UUID,
    data: TaxRuleWrite,
    scope: TaxRuleUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TaxRuleResponse]:
    row = TaxRuleService(db).update_rule(
        rule_id,
        data,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=TaxRuleResponse.model_validate(row))


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tax_rule(
    rule_id: UUID,
    scope: TaxRuleDeleteScope,
    db: Session = Depends(get_db),
) -> Response:
    TaxRuleService(db).delete_rule(
        rule_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/rules/{rule_id}/restore", response_model=ApiResponse[TaxRuleResponse])
def restore_tax_rule(
    rule_id: UUID,
    scope: TaxRuleRestoreScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TaxRuleResponse]:
    row = TaxRuleService(db).restore_rule(
        rule_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=TaxRuleResponse.model_validate(row))


@router.get("/rule-conditions", response_model=ApiResponse[list[TaxRuleConditionResponse]])
def list_tax_rule_conditions(
    scope: TaxRuleViewScope,
    rule_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[list[TaxRuleConditionResponse]]:
    rows = TaxRuleService(db).list_conditions(firm_scope=scope.firm_id, rule_id=rule_id)
    return ApiResponse(data=[TaxRuleConditionResponse.model_validate(row) for row in rows])


@router.get("/rule-priorities", response_model=ApiResponse[list[TaxRulePriorityRecord]])
def list_tax_rule_priorities(
    scope: TaxRuleViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[TaxRulePriorityRecord]]:
    return ApiResponse(data=TaxRuleService(db).list_priorities(firm_scope=scope.firm_id))


@router.get("/rule-history", response_model=ApiResponse[list[TaxRuleResponse]])
def list_tax_rule_history(
    scope: TaxRuleViewScope,
    code: str | None = None,
    version_group_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[list[TaxRuleResponse]]:
    rows = TaxRuleService(db).rule_history(
        firm_scope=scope.firm_id,
        code=code,
        version_group_id=version_group_id,
    )
    return ApiResponse(data=[TaxRuleResponse.model_validate(row) for row in rows])


@router.get("/execution-logs", response_model=ApiResponse[list[TaxRuleExecutionLogResponse]])
def list_tax_rule_execution_logs(
    scope: TaxRuleViewScope,
    limit: int = Query(default=200, ge=1, le=2000),
    matched_rule_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[list[TaxRuleExecutionLogResponse]]:
    rows = TaxRuleService(db).list_execution_logs(
        firm_scope=scope.firm_id,
        limit=limit,
        matched_rule_id=matched_rule_id,
    )
    return ApiResponse(
        data=[TaxRuleExecutionLogResponse.model_validate(row) for row in rows]
    )


@router.post("/simulate", response_model=ApiResponse[TaxRuleSimulationResponse])
def simulate_tax_rule(
    data: TaxRuleSimulationRequest,
    scope: TaxRuleSimulateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TaxRuleSimulationResponse]:
    return ApiResponse(
        data=TaxRuleService(db).simulate(
            data,
            firm_scope=scope.firm_id,
            actor_id=scope.actor_id,
        )
    )


@router.get("/rules/export")
def export_tax_rules(
    scope: TaxExportScope,
    search: str | None = None,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    text = TaxRuleService(db).export_rules_csv(
        firm_scope=scope.firm_id,
        search=search,
    )
    return StreamingResponse(
        iter([text]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="tax_rules.csv"'},
    )


@router.post(
    "/rules/import",
    response_model=ApiResponse[list[TaxRuleResponse]],
    status_code=status.HTTP_201_CREATED,
)
def import_tax_rules(
    data: TaxRuleImportRequest,
    scope: TaxImportScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[TaxRuleResponse]]:
    rows = TaxRuleService(db).import_rules(
        data.rules,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=[TaxRuleResponse.model_validate(row) for row in rows])


@router.post(
    "/legacy/import-csv",
    response_model=ApiResponse[list[TaxMigrationMappingResponse]],
    status_code=status.HTTP_201_CREATED,
)
def import_legacy_tax_mapping_csv(
    scope: TaxImportScope,
    payload: str = Body(..., media_type="text/plain"),
    db: Session = Depends(get_db),
) -> ApiResponse[list[TaxMigrationMappingResponse]]:
    reader = csv.DictReader(StringIO(payload))
    rows: list[TaxMigrationMappingResponse] = []
    service = TaxFrameworkService(db)
    for record in reader:
        if not (record.get("LegacyTaxCode") or "").strip():
            continue
        mapping = service.create_migration_mapping(
            TaxMigrationMappingWrite(
                legacy_tax_code=(record.get("LegacyTaxCode") or "").strip(),
                legacy_tax_name=(record.get("LegacyTaxName") or "").strip(),
                source_system=(record.get("SourceSystem") or "").strip() or None,
                legacy_rate=(
                    (record.get("LegacyRate") or "").strip() or None
                ),
                target_tax_profile_id=(
                    UUID(record["TargetTaxProfileId"])
                    if (record.get("TargetTaxProfileId") or "").strip()
                    else None
                ),
                keep_historical=(record.get("KeepHistorical") or "true").strip().lower()
                in {"1", "true", "yes"},
                status=((record.get("Status") or "ACTIVE").strip().upper()),
                notes=(record.get("Notes") or "").strip() or None,
            ),
            firm_id=scope.firm_id,
            actor_id=scope.actor_id,
        )
        rows.append(TaxMigrationMappingResponse.model_validate(mapping))
    return ApiResponse(data=rows)
