"""FastAPI routes for authentication, RBAC, user, and membership management."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies.settings import get_request_settings
from app.core.config.settings import Settings
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.core.security.authorization import (
    Principal,
    require_any_permission,
    require_authenticated,
    require_permission,
    require_platform_admin,
)
from app.identity.schemas import (
    ChangePasswordRequest,
    IdentifierList,
    LoginRequest,
    MyFirmResponse,
    PermissionCreate,
    PermissionResponse,
    PermissionUpdate,
    RefreshRequest,
    RoleCreate,
    RoleResponse,
    RoleUpdate,
    TokenResponse,
    UserCreate,
    UserFirmAssignments,
    UserFirmResponse,
    UserPreferencesResponse,
    UserPreferencesUpdate,
    UserResponse,
    UserUpdate,
)
from app.identity.services import IdentityService

router = APIRouter(prefix="/api/v1", responses=STANDARD_ERROR_RESPONSES)
UserViewPrincipal = Annotated[Principal, Depends(require_permission("USER_VIEW"))]
UserCreatePrincipal = Annotated[Principal, Depends(require_permission("USER_CREATE"))]
UserUpdatePrincipal = Annotated[Principal, Depends(require_permission("USER_UPDATE"))]
UserDeletePrincipal = Annotated[Principal, Depends(require_permission("USER_DELETE"))]
UserRoleAssignmentPrincipal = Annotated[
    Principal, Depends(require_permission("ROLE_ASSIGN"))
]
UserRoleReadPrincipal = Annotated[
    Principal, Depends(require_any_permission("USER_VIEW", "ROLE_VIEW"))
]
UserFirmAssignmentPrincipal = Annotated[
    Principal, Depends(require_permission("USER_UPDATE", "FIRM_VIEW"))
]
RoleViewPrincipal = Annotated[Principal, Depends(require_permission("ROLE_VIEW"))]
RoleCreatePrincipal = Annotated[Principal, Depends(require_permission("ROLE_CREATE"))]
RoleUpdatePrincipal = Annotated[Principal, Depends(require_permission("ROLE_UPDATE"))]
RoleDeletePrincipal = Annotated[Principal, Depends(require_permission("ROLE_DELETE"))]
RolePermissionAssignmentPrincipal = Annotated[
    Principal, Depends(require_permission("ROLE_ASSIGN"))
]
RolePermissionReadPrincipal = Annotated[
    Principal, Depends(require_permission("PERMISSION_ASSIGN"))
]
PermissionViewPrincipal = Annotated[
    Principal, Depends(require_permission("PERMISSION_VIEW"))
]
PermissionCreatePrincipal = Annotated[
    Principal, Depends(require_permission("PERMISSION_CREATE"))
]
PermissionUpdatePrincipal = Annotated[
    Principal, Depends(require_permission("PERMISSION_UPDATE"))
]
PermissionDeletePrincipal = Annotated[
    Principal, Depends(require_permission("PERMISSION_DELETE"))
]
PlatformPrincipal = Annotated[Principal, Depends(require_platform_admin())]


def _service(db: Session, settings: Settings) -> IdentityService:
    """Construct a request-scoped identity service."""
    return IdentityService(db, settings)


def _actor_id(principal: Principal) -> UUID:
    """Require UUID-backed user principals for mutation audit attribution."""
    if not isinstance(principal.subject, UUID):
        raise RuntimeError("Platform administration requires a user principal.")
    return principal.subject


def _firm_scope(principal: Principal) -> UUID | None:
    """Return tenant scope for firm principals and global scope for platform admins."""
    return None if principal.is_platform_admin else principal.firm_id


@router.post(
    "/auth/login", response_model=ApiResponse[TokenResponse], tags=["Authentication"]
)
def login(
    data: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[TokenResponse]:
    """Authenticate a user and return an access plus refresh token pair."""
    client = request.client
    result = _service(db, settings).login(
        data.email,
        data.password,
        client_ip=client.host if client else None,
        user_agent=request.headers.get("User-Agent"),
    )
    return ApiResponse(data=result)


@router.post(
    "/auth/refresh", response_model=ApiResponse[TokenResponse], tags=["Authentication"]
)
def refresh(
    data: RefreshRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[TokenResponse]:
    """Rotate a refresh token and issue its replacement pair."""
    return ApiResponse(data=_service(db, settings).refresh(data.refresh_token))


@router.post(
    "/auth/logout", status_code=status.HTTP_204_NO_CONTENT, tags=["Authentication"]
)
def logout(
    data: RefreshRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> Response:
    """Revoke the submitted refresh token; the operation is safely idempotent."""
    _service(db, settings).logout(data.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/auth/change-password", response_model=ApiResponse[None], tags=["Authentication"]
)
def change_password(
    data: ChangePasswordRequest,
    principal: Annotated[Principal, Depends(require_authenticated())],
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[None]:
    """Change the authenticated user's password and revoke existing refresh tokens."""
    _service(db, settings).change_password(
        _actor_id(principal), data.current_password, data.new_password
    )
    return ApiResponse(data=None, message="Password changed. Sign in again.")


@router.get(
    "/me/preferences",
    response_model=ApiResponse[UserPreferencesResponse],
    tags=["User preferences"],
)
def get_my_preferences(
    principal: Annotated[Principal, Depends(require_authenticated())],
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[UserPreferencesResponse]:
    """Return the authenticated user's versioned preference document."""
    preferences = _service(db, settings).get_user_preferences(_actor_id(principal))
    return ApiResponse(data=UserPreferencesResponse.model_validate(preferences))


@router.patch(
    "/me/preferences",
    response_model=ApiResponse[UserPreferencesResponse],
    tags=["User preferences"],
)
def update_my_preferences(
    data: UserPreferencesUpdate,
    principal: Annotated[Principal, Depends(require_authenticated())],
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[UserPreferencesResponse]:
    """Update only the authenticated user's preferences partially."""
    preferences = _service(db, settings).update_user_preferences(
        _actor_id(principal), data
    )
    return ApiResponse(data=UserPreferencesResponse.model_validate(preferences))


@router.post(
    "/me/preferences/reset",
    response_model=ApiResponse[UserPreferencesResponse],
    tags=["User preferences"],
)
def reset_my_preferences(
    principal: Annotated[Principal, Depends(require_authenticated())],
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[UserPreferencesResponse]:
    """Restore the authenticated user's preferences to current defaults."""
    preferences = _service(db, settings).reset_user_preferences(_actor_id(principal))
    return ApiResponse(data=UserPreferencesResponse.model_validate(preferences))


@router.get(
    "/me/firms",
    response_model=ApiResponse[list[MyFirmResponse]],
    tags=["User preferences"],
)
def list_my_firms(
    principal: Annotated[Principal, Depends(require_authenticated())],
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[list[MyFirmResponse]]:
    """Return active firms assigned to the authenticated user."""
    rows = _service(db, settings).list_my_firms(_actor_id(principal))
    return ApiResponse(
        data=[
            MyFirmResponse(
                id=firm.id,
                code=firm.code,
                name=firm.name,
                is_primary=membership.is_primary,
            )
            for membership, firm in rows
        ]
    )


@router.get("/users", response_model=PaginatedResponse[UserResponse], tags=["Users"])
def list_users(
    principal: UserViewPrincipal,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    sort_by: Literal["email", "full_name", "created_at"] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> PaginatedResponse[UserResponse]:
    """List users using whitelisted filtering, paging, and sorting fields."""
    params = PaginationParams(page=page, page_size=page_size)
    rows, total = _service(db, settings).list_users(
        params.page,
        params.page_size,
        search,
        sort_by,
        sort_direction == "desc",
        _firm_scope(principal),
    )
    return PaginatedResponse(
        data=[UserResponse.model_validate(row) for row in rows],
        pagination=params.metadata(total),
    )


@router.post(
    "/users",
    response_model=ApiResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
    tags=["Users"],
)
def create_user(
    data: UserCreate,
    principal: UserCreatePrincipal,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[UserResponse]:
    """Provision an interactive user."""
    user = _service(db, settings).create_user(
        data, _actor_id(principal), _firm_scope(principal)
    )
    return ApiResponse(data=UserResponse.model_validate(user))


@router.get(
    "/users/{user_id}", response_model=ApiResponse[UserResponse], tags=["Users"]
)
def get_user(
    user_id: UUID,
    principal: UserViewPrincipal,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[UserResponse]:
    """Retrieve a visible user."""
    return ApiResponse(
        data=UserResponse.model_validate(
            _service(db, settings)._get_user(user_id, _firm_scope(principal))
        )
    )


@router.patch(
    "/users/{user_id}", response_model=ApiResponse[UserResponse], tags=["Users"]
)
def update_user(
    user_id: UUID,
    data: UserUpdate,
    principal: UserUpdatePrincipal,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[UserResponse]:
    """Update user status, expiry, name, or clear a lock."""
    user = _service(db, settings).update_user(
        user_id, data, _actor_id(principal), _firm_scope(principal)
    )
    return ApiResponse(data=UserResponse.model_validate(user))


@router.delete(
    "/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Users"]
)
def delete_user(
    user_id: UUID,
    principal: UserDeletePrincipal,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> Response:
    """Soft delete a user and revoke active refresh tokens."""
    _service(db, settings).delete_user(
        user_id, _actor_id(principal), _firm_scope(principal)
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/users/{user_id}/roles", response_model=ApiResponse[None], tags=["Users"])
def set_user_roles(
    user_id: UUID,
    data: IdentifierList,
    principal: UserRoleAssignmentPrincipal,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[None]:
    """Replace a user's role assignment collection."""
    _service(db, settings).set_user_roles(
        user_id, data.ids, _actor_id(principal), _firm_scope(principal)
    )
    return ApiResponse(data=None)


@router.get(
    "/users/{user_id}/roles",
    response_model=ApiResponse[IdentifierList],
    tags=["Users"],
)
def list_user_roles(
    user_id: UUID,
    principal: UserRoleReadPrincipal,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[IdentifierList]:
    """List role assignment identifiers for one user."""
    return ApiResponse(
        data=IdentifierList(
            ids=_service(db, settings).list_user_role_ids(
                user_id, _firm_scope(principal)
            )
        )
    )


@router.get(
    "/users/{user_id}/firms",
    response_model=ApiResponse[list[UserFirmResponse]],
    tags=["Users"],
)
def list_user_firms(
    user_id: UUID,
    principal: RoleViewPrincipal,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[list[UserFirmResponse]]:
    """List a user's firm memberships."""
    rows = _service(db, settings).list_user_firms(user_id)
    return ApiResponse(data=[UserFirmResponse.model_validate(row) for row in rows])


@router.put(
    "/users/{user_id}/firms",
    response_model=ApiResponse[list[UserFirmResponse]],
    tags=["Users"],
)
def set_user_firms(
    user_id: UUID,
    data: UserFirmAssignments,
    principal: PlatformPrincipal,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[list[UserFirmResponse]]:
    """Replace a user's active/primary firm memberships."""
    rows = _service(db, settings).set_user_firms(
        user_id, data.assignments, _actor_id(principal)
    )
    return ApiResponse(data=[UserFirmResponse.model_validate(row) for row in rows])


@router.get("/roles", response_model=PaginatedResponse[RoleResponse], tags=["Roles"])
def list_roles(
    principal: PlatformPrincipal,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    sort_by: Literal["code", "name", "created_at"] = "code",
    sort_direction: Literal["asc", "desc"] = "asc",
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> PaginatedResponse[RoleResponse]:
    """List system and custom roles with approved collection query fields."""
    params = PaginationParams(page=page, page_size=page_size)
    rows, total = _service(db, settings).list_roles(
        params.page,
        params.page_size,
        search,
        sort_by,
        sort_direction == "desc",
        _firm_scope(principal),
    )
    return PaginatedResponse(
        data=[RoleResponse.model_validate(item) for item in rows],
        pagination=params.metadata(total),
    )


@router.post(
    "/roles",
    response_model=ApiResponse[RoleResponse],
    status_code=status.HTTP_201_CREATED,
    tags=["Roles"],
)
def create_role(
    data: RoleCreate,
    principal: RoleCreatePrincipal,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[RoleResponse]:
    """Create a custom role."""
    return ApiResponse(
        data=RoleResponse.model_validate(
            _service(db, settings).create_role(
                data, _actor_id(principal), _firm_scope(principal)
            )
        )
    )


@router.get(
    "/roles/{role_id}", response_model=ApiResponse[RoleResponse], tags=["Roles"]
)
def get_role(
    role_id: UUID,
    principal: RoleViewPrincipal,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[RoleResponse]:
    """Retrieve a system or custom role."""
    return ApiResponse(
        data=RoleResponse.model_validate(
            _service(db, settings).get_role(role_id, _firm_scope(principal))
        )
    )


@router.patch(
    "/roles/{role_id}", response_model=ApiResponse[RoleResponse], tags=["Roles"]
)
def update_role(
    role_id: UUID,
    data: RoleUpdate,
    principal: RoleUpdatePrincipal,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[RoleResponse]:
    """Update a custom role."""
    return ApiResponse(
        data=RoleResponse.model_validate(
            _service(db, settings).update_role(
                role_id, data, _actor_id(principal), _firm_scope(principal)
            )
        )
    )


@router.delete(
    "/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Roles"]
)
def delete_role(
    role_id: UUID,
    principal: RoleDeletePrincipal,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> Response:
    """Soft delete a custom role."""
    _service(db, settings).delete_role(
        role_id, _actor_id(principal), _firm_scope(principal)
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/roles/{role_id}/permissions", response_model=ApiResponse[None], tags=["Roles"]
)
def set_role_permissions(
    role_id: UUID,
    data: IdentifierList,
    principal: RolePermissionAssignmentPrincipal,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[None]:
    """Replace role permission assignments."""
    _service(db, settings).set_role_permissions(
        role_id, data.ids, _actor_id(principal), _firm_scope(principal)
    )
    return ApiResponse(data=None)


@router.get(
    "/roles/{role_id}/permissions",
    response_model=ApiResponse[IdentifierList],
    tags=["Roles"],
)
def list_role_permissions(
    role_id: UUID,
    principal: RolePermissionReadPrincipal,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[IdentifierList]:
    """List permission assignment identifiers for a role."""
    return ApiResponse(
        data=IdentifierList(
            ids=_service(db, settings).list_role_permission_ids(
                role_id, _firm_scope(principal)
            )
        )
    )


@router.get(
    "/permissions",
    response_model=PaginatedResponse[PermissionResponse],
    tags=["Permissions"],
)
def list_permissions(
    principal: PermissionViewPrincipal,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    sort_by: Literal["code", "name", "created_at"] = "code",
    sort_direction: Literal["asc", "desc"] = "asc",
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> PaginatedResponse[PermissionResponse]:
    """List permissions with approved collection query fields."""
    params = PaginationParams(page=page, page_size=page_size)
    rows, total = _service(db, settings).list_permissions(
        params.page,
        params.page_size,
        search,
        sort_by,
        sort_direction == "desc",
        _firm_scope(principal),
    )
    return PaginatedResponse(
        data=[PermissionResponse.model_validate(item) for item in rows],
        pagination=params.metadata(total),
    )


@router.post(
    "/permissions",
    response_model=ApiResponse[PermissionResponse],
    status_code=status.HTTP_201_CREATED,
    tags=["Permissions"],
)
def create_permission(
    data: PermissionCreate,
    principal: PermissionViewPrincipal,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[PermissionResponse]:
    """Create a permission."""
    return ApiResponse(
        data=PermissionResponse.model_validate(
            _service(db, settings).create_permission(data, _actor_id(principal))
        )
    )


@router.get(
    "/permissions/{permission_id}",
    response_model=ApiResponse[PermissionResponse],
    tags=["Permissions"],
)
def get_permission(
    permission_id: UUID,
    principal: PlatformPrincipal,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[PermissionResponse]:
    """Retrieve a visible permission."""
    return ApiResponse(
        data=PermissionResponse.model_validate(
            _service(db, settings).get_permission(
                permission_id, _firm_scope(principal)
            )
        )
    )


@router.patch(
    "/permissions/{permission_id}",
    response_model=ApiResponse[PermissionResponse],
    tags=["Permissions"],
)
def update_permission(
    permission_id: UUID,
    data: PermissionUpdate,
    principal: PlatformPrincipal,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[PermissionResponse]:
    """Update a permission."""
    return ApiResponse(
        data=PermissionResponse.model_validate(
            _service(db, settings).update_permission(
                permission_id, data, _actor_id(principal)
            )
        )
    )


@router.delete(
    "/permissions/{permission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Permissions"],
)
def delete_permission(
    permission_id: UUID,
    principal: PlatformPrincipal,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> Response:
    """Soft delete an unassigned permission."""
    _service(db, settings).delete_permission(permission_id, _actor_id(principal))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
