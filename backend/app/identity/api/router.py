"""FastAPI routes for authentication, RBAC, user, and membership management."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies.settings import get_request_settings
from app.core.config.settings import Settings
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.exceptions import ValidationError
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
from app.identity.models import UserTemplate
from app.identity.schemas import (
    ChangePasswordRequest,
    IdentifierList,
    LoginRequest,
    MeResponse,
    MyFirmResponse,
    MyRoleResponse,
    PermissionCreate,
    PermissionResponse,
    PermissionUpdate,
    PrimaryFirmUpdate,
    RefreshRequest,
    RoleCreate,
    RoleResponse,
    RoleUpdate,
    TokenResponse,
    UserCloneRequest,
    UserCreate,
    UserFirmAssignments,
    UserFirmResponse,
    UserLookupResponse,
    UserPreferencesResponse,
    UserPreferencesUpdate,
    UserProfileFields,
    UserResponse,
    UserTemplateApply,
    UserTemplateCreate,
    UserTemplateResponse,
    UserTemplateUpdate,
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
PlatformPrincipal = Annotated[Principal, Depends(require_platform_admin())]


def _service(db: Session, settings: Settings) -> IdentityService:
    """Construct a request-scoped identity service."""
    return IdentityService(db, settings)


def _actor_id(principal: Principal) -> UUID:
    """Require UUID-backed user principals for mutation audit attribution."""
    if not isinstance(principal.subject, UUID):
        raise RuntimeError("Platform administration requires a user principal.")
    return principal.subject


def _firms_the_caller_may_staff(principal: Principal) -> frozenset[UUID] | None:
    """Return the firms this caller may put people into, or None for all.

    A platform administrator whose designation reaches every firm gets None,
    which is what they have always had. Everybody else gets the firms where
    they themselves hold `USER_CREATE` -- **not** the firms they merely belong
    to. Somebody who is an administrator in one firm and a sales executive in
    another must not be able to staff the second, and mere membership cannot
    tell those apart.

    Read from the token's own `firm_permissions` map, which is the same answer
    the desktop resolves its menus from. It cannot go stale behind a role
    change: `set_user_roles` bumps `authorization_version`, and
    `get_current_principal` refuses a token whose version has moved.
    """
    if principal.may_act_in_any_firm:
        return None
    return frozenset(
        firm_id
        for firm_id, codes in principal.firm_permissions.items()
        if "USER_CREATE" in codes
    )


def _firm_scope(principal: Principal) -> UUID | None:
    """Return tenant scope for firm principals and global scope for platform admins."""
    return None if principal.is_platform_admin else principal.firm_id


def _requested_firm_scope(principal: Principal, firm_id: UUID | None) -> UUID | None:
    """Resolve which firm a user list is being asked about.

    A platform administrator sees every user, which makes "who works at
    WHOLE01?" a question they had no way to ask: the only firm filter was the
    caller's own `X-Firm-ID`, and answering it meant switching into the firm.

    A firm caller may name only the firm they are working in. Naming another
    is **refused rather than ignored** -- a request that quietly answers about
    a different firm than the one asked for is how somebody comes to believe
    an account exists somewhere it does not.
    """
    scope = _firm_scope(principal)
    if firm_id is None:
        return scope
    if scope is not None and firm_id != scope:
        raise ValidationError(
            "A user list can only be filtered by the firm you are working in. "
            "Switch firms to see another one's people."
        )
    return firm_id


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
    """Return the firms this user may work in.

    A platform administrator whose reach is `ALL_FIRMS` gets every active
    firm, not only the ones somebody gave them a membership row in. Their
    designation already exempts them from the membership check, so this list
    was the only thing standing between them and the firms they may act in --
    and the bootstrap administrator, seeded with no memberships at all, was
    offered an empty switcher while its token carried every permission code.

    A `PLATFORM` administrator is deliberately not widened: they are refused
    firm-owned routes, so a switcher full of firms would offer them nothing
    but 403s.
    """
    rows = _service(db, settings).list_my_firms(
        _actor_id(principal), every_firm=principal.may_act_in_any_firm
    )
    return ApiResponse(
        data=[
            MyFirmResponse(
                id=firm.id,
                code=firm.code,
                name=firm.name,
                # A firm reached by the designation has no membership row, so
                # it is nobody's primary.
                is_primary=membership is not None and membership.is_primary,
            )
            for membership, firm in rows
        ]
    )


@router.get("/me", response_model=ApiResponse[MeResponse], tags=["User preferences"])
def get_me(
    principal: Annotated[Principal, Depends(require_authenticated())],
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[MeResponse]:
    """Return who is signed in.

    Being signed in is the whole gate. `GET /users/{id}` needs `USER_VIEW`,
    which most people do not hold, and the token carries no name -- so the
    desktop's user menu could show nothing but the address typed at the login
    form, and after a restored session not even that.
    """
    return ApiResponse(data=_me_response(_service(db, settings), _actor_id(principal)))


def _me_response(service: IdentityService, user_id: UUID) -> MeResponse:
    """Assemble what a person may know about themselves."""
    user, is_platform_admin, primary = service.describe_me(user_id)
    return MeResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_platform_admin=is_platform_admin,
        primary_firm_id=primary,
        last_login_at=user.last_login_at,
        profile=UserProfileFields.model_validate(user),
        roles=[
            MyRoleResponse(
                code=role.code,
                name=role.name,
                firm_id=firm.id if firm is not None else None,
                firm_code=firm.code if firm is not None else None,
            )
            for role, firm in service.list_my_roles(user_id)
        ],
    )


@router.put(
    "/me/primary-firm",
    response_model=ApiResponse[MeResponse],
    tags=["User preferences"],
)
def set_my_primary_firm(
    data: PrimaryFirmUpdate,
    principal: Annotated[Principal, Depends(require_authenticated())],
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[MeResponse]:
    """Choose the firm to land in at sign-in, among the firms this user belongs to.

    Where a person lands is their own decision. The administrator's route,
    `PUT /users/{id}/firms`, sets the same flag but replaces the whole
    membership list and is held to the caller's reach; this touches the flag
    alone, for the caller alone.
    """
    service = _service(db, settings)
    service.set_own_primary_firm(_actor_id(principal), data.firm_id)
    return ApiResponse(data=_me_response(service, _actor_id(principal)))


@router.get("/users", response_model=PaginatedResponse[UserResponse], tags=["Users"])
def list_users(
    principal: UserViewPrincipal,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: str | None = None,
    firm_id: UUID | None = None,
    deleted_only: bool = False,
    sort_by: Literal["email", "full_name", "created_at"] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> PaginatedResponse[UserResponse]:
    """List users using whitelisted filtering, paging, and sorting fields.

    `firm_id` narrows the list to that firm's **active** members, which is the
    question a platform administrator could not previously ask without
    switching into the firm. It is refused for a firm caller naming anybody
    else's firm; see `_requested_firm_scope`.

    `deleted_only` lists soft-deleted users **instead of** live ones, so one
    can be found and restored -- a list of everybody with the deleted mixed
    in is not what "show me the deleted" asks for. Honoured for a platform
    administrator only; a firm caller's list stays live rows whatever they
    send, since a deleted person's memberships still place them in the firm.
    """
    params = PaginationParams(page=page, page_size=page_size)
    scope = _requested_firm_scope(principal, firm_id)
    rows, total = _service(db, settings).list_users(
        params.page,
        params.page_size,
        search,
        sort_by,
        sort_direction == "desc",
        scope,
        deleted_only=deleted_only and principal.is_platform_admin,
    )
    # One query for the page rather than one per row. Without it the grid
    # cannot know whom it may edit, and offers a form that cannot save.
    shared = _service(db, settings).shared_user_ids([row.id for row in rows], scope)
    return PaginatedResponse(
        data=[
            UserResponse.model_validate(row).model_copy(
                update={"belongs_to_other_firms": row.id in shared}
            )
            for row in rows
        ],
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
    "/users/lookup",
    response_model=PaginatedResponse[UserLookupResponse],
    tags=["Users"],
)
def lookup_users(
    principal: UserCreatePrincipal,
    q: Annotated[str, Query(max_length=320)] = "",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> PaginatedResponse[UserLookupResponse]:
    """Find somebody who already has an account, to hire them into this firm.

    **Declared above `/users/{user_id}` and it must stay there.** FastAPI
    matches in declaration order, so a literal path below `/{user_id}` is read
    as a user id and answers 422 "Input should be a valid UUID". That has
    happened ten times in this repository;
    `tests/unit/test_route_declaration_order.py` fails the build on the next.

    Gated on `USER_CREATE`: this exists in order to hire, and whoever may not
    open an account has no use for it. `USER_VIEW` deliberately does not
    reach it -- reading your own firm's people and reaching across firms are
    different privileges.

    A firm caller must send at least three characters and gets at most ten,
    whatever `page` says. A platform caller may send nothing and gets
    everybody not yet in the firm named by `X-Firm-ID`, paged -- see
    `IdentityService.lookup_users` for why the two differ.
    """
    params = PaginationParams(page=page, page_size=page_size)
    found, total = _service(db, settings).lookup_users(
        q,
        _firm_scope(principal),
        hiring_firm_id=principal.firm_id,
        page=params.page,
        page_size=params.page_size,
    )
    return PaginatedResponse(
        data=[
            UserLookupResponse(
                id=user.id,
                full_name=user.full_name,
                email=user.email,
                already_a_member=is_member,
            )
            for user, is_member in found
        ],
        pagination=params.metadata(total),
    )


@router.get(
    "/users/{user_id}", response_model=ApiResponse[UserResponse], tags=["Users"]
)
def get_user(
    user_id: UUID,
    principal: UserViewPrincipal,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[UserResponse]:
    """Retrieve a visible user.

    A platform caller may read a deleted one -- it is how a deleted user is
    inspected before being restored -- and the response says `is_deleted`.
    """
    scope = _firm_scope(principal)
    service = _service(db, settings)
    user = service._get_user(user_id, scope, include_deleted=scope is None)
    return ApiResponse(
        data=UserResponse.model_validate(user).model_copy(
            update={
                "belongs_to_other_firms": bool(
                    service.shared_user_ids([user.id], scope)
                )
            }
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


@router.post(
    "/users/{user_id}/restore",
    response_model=ApiResponse[UserResponse],
    tags=["Users"],
)
def restore_user(
    user_id: UUID,
    principal: PlatformPrincipal,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[UserResponse]:
    """Bring a soft-deleted user back, with their old firms and roles.

    Platform administrators only. Deletion is firm-scoped for a firm
    administrator, but a deleted user is invisible to a firm's grid and their
    memberships are platform facts, so the way back is the platform's. Refused
    when a live account has since taken the address.
    """
    user = _service(db, settings).restore_user(user_id, _actor_id(principal))
    return ApiResponse(data=UserResponse.model_validate(user))


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


@router.put(
    "/users/{user_id}/firms/{firm_id}/roles",
    response_model=ApiResponse[None],
    tags=["Users"],
)
def set_user_firm_roles(
    user_id: UUID,
    firm_id: UUID,
    data: IdentifierList,
    principal: UserRoleAssignmentPrincipal,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[None]:
    """Replace what one user does in one firm.

    The only route that grants a firm-tier role. A platform administrator
    names the firm rather than having the grant apply everywhere by omission;
    a firm administrator is held to the firms they may staff, and their edit
    of a row is what an override amounts to -- there is no precedence rule,
    because every grant is a row in one firm.
    """
    _service(db, settings).set_user_firm_roles(
        user_id,
        firm_id,
        data.ids,
        _actor_id(principal),
        _firms_the_caller_may_staff(principal),
    )
    return ApiResponse(data=None)


@router.get(
    "/users/{user_id}/global-roles",
    response_model=ApiResponse[IdentifierList],
    tags=["Users"],
)
def list_user_global_roles(
    user_id: UUID,
    principal: RoleViewPrincipal,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[IdentifierList]:
    """List the roles one user holds in every firm.

    Readable by a firm administrator and not writable by them: these apply in
    their firm, so hiding them would under-report what the person can do
    there, and letting them edit one would undo a platform decision.
    """
    return ApiResponse(
        data=IdentifierList(
            ids=_service(db, settings).list_user_global_role_ids(user_id)
        )
    )


@router.get(
    "/users/{user_id}/firms/{firm_id}/roles",
    response_model=ApiResponse[IdentifierList],
    tags=["Users"],
)
def list_user_firm_roles(
    user_id: UUID,
    firm_id: UUID,
    principal: RoleViewPrincipal,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[IdentifierList]:
    """List the roles one user holds in one firm.

    Held to the same reach as the write twin: a firm administrator reads the
    firms they may staff, not every firm a shared user belongs to. It used to
    answer for any firm, which disclosed what a person does elsewhere to
    anybody holding `ROLE_VIEW` and a user id.
    """
    return ApiResponse(
        data=IdentifierList(
            ids=_service(db, settings).list_user_firm_role_ids(
                user_id,
                firm_id,
                _firm_scope(principal),
                allowed_firm_ids=_firms_the_caller_may_staff(principal),
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
    """List the firm memberships this caller may see.

    Scoped to the caller's reach. It returned **every** membership on a route
    gated only by `ROLE_VIEW`, so any firm administrator holding a user id
    could read which firms that person belongs to -- the one fact a firm must
    not learn about another, leaking for every user rather than only shared
    ones. A platform caller's reach is None and still sees them all.
    """
    rows = _service(db, settings).list_user_firms(
        user_id, _firms_the_caller_may_staff(principal)
    )
    return ApiResponse(data=[UserFirmResponse.model_validate(row) for row in rows])


@router.put(
    "/users/{user_id}/firms",
    response_model=ApiResponse[list[UserFirmResponse]],
    tags=["Users"],
)
def set_user_firms(
    user_id: UUID,
    data: UserFirmAssignments,
    # `USER_UPDATE`, not the platform designation. It was the designation, on
    # the reasoning that which firms a person belongs to is a cross-firm fact
    # -- true, and it does not follow that only a platform administrator may
    # touch it. An administrator of two firms putting a new hire in both is
    # the ordinary case, and they were refused. The cross-firm part is handled
    # by reach instead: they may name only firms they themselves may staff,
    # and memberships outside that are carried through untouched.
    principal: UserUpdatePrincipal,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[list[UserFirmResponse]]:
    """Set a user's memberships among the firms this caller may staff."""
    rows = _service(db, settings).set_user_firms(
        user_id,
        data.assignments,
        _actor_id(principal),
        _firms_the_caller_may_staff(principal),
    )
    return ApiResponse(data=[UserFirmResponse.model_validate(row) for row in rows])


@router.get("/roles", response_model=PaginatedResponse[RoleResponse], tags=["Roles"])
def list_roles(
    # `ROLE_VIEW`, not the platform designation. This was the only one of the
    # four role endpoints gated on the designation -- `get_role`, `create_role`
    # and `update_role` all take the permission -- and the only one of the
    # three identity lists, beside `list_users` and `list_permissions`. So
    # `ROLE_VIEW` was seeded, granted to `FIRM_ADMIN`, honoured everywhere
    # except the one place a firm administrator would start, and the firm
    # filtering below was written for a caller who could never reach it.
    principal: RoleViewPrincipal,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
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


def _template_response(template: UserTemplate) -> UserTemplateResponse:
    """Render a template with the roles it bundles.

    The codes travel beside the ids because the screen offering a template
    shows what it does, and a list of UUIDs says nothing to anybody.
    """
    live = [row for row in template.template_roles if not row.is_deleted]
    return UserTemplateResponse(
        id=template.id,
        code=template.code,
        name=template.name,
        description=template.description,
        firm_id=template.firm_id,
        is_active=template.is_active,
        is_system=template.is_system,
        role_ids=[row.role_id for row in live],
        role_codes=sorted(row.role.code for row in live if row.role is not None),
    )


@router.get(
    "/user-templates",
    response_model=PaginatedResponse[UserTemplateResponse],
    tags=["User templates"],
)
def list_user_templates(
    principal: RoleViewPrincipal,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: str | None = None,
    sort_by: Literal["code", "name", "created_at"] = "code",
    sort_direction: Literal["asc", "desc"] = "asc",
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> PaginatedResponse[UserTemplateResponse]:
    """List the job templates this caller may offer."""
    params = PaginationParams(page=page, page_size=page_size)
    rows, total = _service(db, settings).list_user_templates(
        params.page,
        params.page_size,
        search,
        sort_by,
        sort_direction == "desc",
        _firm_scope(principal),
    )
    return PaginatedResponse(
        data=[_template_response(item) for item in rows],
        pagination=params.metadata(total),
    )


@router.post(
    "/user-templates",
    response_model=ApiResponse[UserTemplateResponse],
    status_code=status.HTTP_201_CREATED,
    tags=["User templates"],
)
def create_user_template(
    data: UserTemplateCreate,
    principal: RoleCreatePrincipal,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[UserTemplateResponse]:
    """Create a job template for this scope."""
    return ApiResponse(
        data=_template_response(
            _service(db, settings).create_user_template(
                data, _actor_id(principal), _firm_scope(principal)
            )
        )
    )


@router.get(
    "/user-templates/{template_id}",
    response_model=ApiResponse[UserTemplateResponse],
    tags=["User templates"],
)
def get_user_template(
    template_id: UUID,
    principal: RoleViewPrincipal,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[UserTemplateResponse]:
    """Retrieve one job template."""
    return ApiResponse(
        data=_template_response(
            _service(db, settings).get_user_template(
                template_id, _firm_scope(principal)
            )
        )
    )


@router.patch(
    "/user-templates/{template_id}",
    response_model=ApiResponse[UserTemplateResponse],
    tags=["User templates"],
)
def update_user_template(
    template_id: UUID,
    data: UserTemplateUpdate,
    principal: RoleUpdatePrincipal,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[UserTemplateResponse]:
    """Update a job template."""
    return ApiResponse(
        data=_template_response(
            _service(db, settings).update_user_template(
                template_id, data, _actor_id(principal), _firm_scope(principal)
            )
        )
    )


@router.delete(
    "/user-templates/{template_id}",
    response_model=ApiResponse[None],
    tags=["User templates"],
)
def delete_user_template(
    template_id: UUID,
    principal: RoleDeletePrincipal,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[None]:
    """Retire a job template, leaving every user it created untouched."""
    _service(db, settings).delete_user_template(
        template_id, _actor_id(principal), _firm_scope(principal)
    )
    return ApiResponse(data=None, message="The template was retired.")


@router.post(
    "/users/{user_id}/clone",
    response_model=ApiResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
    tags=["User templates"],
)
def clone_user(
    user_id: UUID,
    data: UserCloneRequest,
    principal: UserRoleAssignmentPrincipal,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[UserResponse]:
    """Hire somebody to do what an existing person does.

    A template is a job somebody wrote down; this is the job somebody is
    already doing. Only access is copied -- the new person starts without the
    source's mobile number, employee code, joining date, photo, password,
    login history or audit trail, because those belong to the person and not
    to the job.

    Gated on `ROLE_ASSIGN`, which is exactly what it does: give somebody a set
    of roles. `USER_CREATE` alone must not reach it, or an administrator who
    may open accounts but not grant access could copy access instead.
    """
    return ApiResponse(
        data=UserResponse.model_validate(
            _service(db, settings).clone_user(
                user_id, data, _actor_id(principal), _firm_scope(principal)
            )
        ),
        message="The new user was created with the same access.",
    )


@router.post(
    "/users/{user_id}/apply-template",
    response_model=ApiResponse[list[UUID]],
    tags=["User templates"],
)
def apply_user_template(
    user_id: UUID,
    data: UserTemplateApply,
    principal: UserRoleAssignmentPrincipal,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[list[UUID]]:
    """Give a user the roles a template bundles.

    What they hold afterwards is an ordinary role set, editable in the ordinary
    way: a template is where an administrator starts, not somewhere they stay.
    """
    return ApiResponse(
        data=_service(db, settings).apply_user_template(
            user_id,
            data.template_id,
            _actor_id(principal),
            _firm_scope(principal),
            data.firm_id,
        ),
        message="The template was applied.",
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
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
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
    # Platform admin, matching `update_permission` and `delete_permission`.
    # This took `PermissionViewPrincipal` -- so the weakest gate in the file
    # created rows in the platform-wide permission catalogue while the two
    # endpoints that merely edit them required a platform administrator.
    #
    # Not exploitable when it was found: `PERMISSION_VIEW` and
    # `PERMISSION_CREATE` are held by the same three roles. It would have
    # become so the first time somebody granted "let them see the catalogue"
    # without meaning "let them add to it", which is a reasonable thing to
    # want and would have opened this silently.
    principal: PlatformPrincipal,
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
            _service(db, settings).get_permission(permission_id, _firm_scope(principal))
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
