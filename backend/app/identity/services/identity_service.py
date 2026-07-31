"""Application services for authentication and platform identity administration."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import cast
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.config.settings import Settings
from app.core.enums import TokenType
from app.core.exceptions import (
    AuthenticationError,
    BusinessRuleError,
    ConflictError,
    ResourceNotFoundError,
)
from app.core.security import JwtService, PasswordSecurity
from app.core.utils.dates import utc_now
from app.core.validation import validate_email, validate_password_policy
from app.firms.models import Firm
from app.identity.models import (
    LoginHistory,
    PasswordHistory,
    Permission,
    PlatformAdmin,
    RefreshToken,
    Role,
    RolePermission,
    User,
    UserFirm,
    UserPreferences,
    UserRole,
)
from app.identity.schemas.api import (
    PermissionCreate,
    PermissionUpdate,
    RoleCreate,
    RoleUpdate,
    TokenResponse,
    UserCreate,
    UserFirmAssignment,
    UserPreferencesUpdate,
    UserUpdate,
)
from app.identity.system_seed import (
    FIRM_ROLE_CODES,
    HIDDEN_SYSTEM_ROLE_CODES,
    PLATFORM_PERMISSION_CODES,
    PLATFORM_ROLE_CODES,
)


class IdentityService:
    """Coordinate identity persistence, security policy, and audit logging."""

    def __init__(self, session: Session, settings: Settings) -> None:
        """Bind the service to one request transaction and configuration."""
        self._session = session
        self._settings = settings
        self._passwords = PasswordSecurity()
        self._jwt = JwtService(settings.jwt)

    def login(
        self,
        email: str,
        password: str,
        *,
        client_ip: str | None,
        user_agent: str | None,
    ) -> TokenResponse:
        """Authenticate credentials, enforce lockout, and issue a token pair."""
        normalized_email = validate_email(email)
        user = self._session.scalar(
            select(User).where(
                User.email == normalized_email, User.is_deleted.is_(False)
            )
        )
        now = utc_now()
        if user is None:
            self._record_login(
                None,
                normalized_email,
                "failed",
                client_ip,
                user_agent,
                "invalid_credentials",
            )
            self._session.commit()
            raise AuthenticationError("Invalid email or password.")
        if user.locked_until is not None and user.locked_until > now:
            self._record_login(
                user.id,
                normalized_email,
                "locked",
                client_ip,
                user_agent,
                "account_locked",
            )
            self._session.commit()
            raise AuthenticationError("Invalid email or password.")
        unavailable = not user.is_active or (
            user.expires_at is not None and user.expires_at <= now
        )
        if unavailable:
            self._record_login(
                user.id,
                normalized_email,
                "failed",
                client_ip,
                user_agent,
                "account_unavailable",
            )
            self._session.commit()
            raise AuthenticationError("Invalid email or password.")
        if user.password_hash == "*":
            bootstrap = self._settings.bootstrap_admin_password
            valid = bootstrap is not None and password == bootstrap.get_secret_value()
            if valid:
                user.password_hash = self._passwords.hash_password(password)
            else:
                self._register_failed_login(user, client_ip, user_agent)
                raise AuthenticationError("Invalid email or password.")
        elif not self._passwords.verify_password(password, user.password_hash):
            self._register_failed_login(user, client_ip, user_agent)
            raise AuthenticationError("Invalid email or password.")
        user.failed_login_attempts, user.locked_until, user.last_login_at = 0, None, now
        self._record_login(
            user.id, normalized_email, "success", client_ip, user_agent, None
        )
        response = self._issue_tokens(user)
        record_audit(
            self._session,
            action="identity.login",
            entity_type="user",
            entity_id=user.id,
            actor_id=user.id,
        )
        self._session.commit()
        return response

    def refresh(self, refresh_token: str) -> TokenResponse:
        """Rotate a valid persisted refresh token and revoke its predecessor."""
        claims = self._jwt.validate_token(
            refresh_token, expected_type=TokenType.REFRESH
        )
        try:
            user_id = UUID(claims.subject)
        except ValueError as error:
            raise AuthenticationError(
                "The refresh token is invalid or expired."
            ) from error
        user = self._get_user(user_id)
        now = utc_now()
        unavailable = not user.is_active or (
            user.expires_at is not None and user.expires_at <= now
        )
        if unavailable:
            raise AuthenticationError("The refresh token is invalid or expired.")
        token_hash = _hash_token(refresh_token)
        result = cast(
            CursorResult[object],
            self._session.execute(
                update(RefreshToken)
                .where(
                    RefreshToken.token_hash == token_hash,
                    RefreshToken.user_id == user.id,
                    RefreshToken.is_deleted.is_(False),
                    RefreshToken.revoked_at.is_(None),
                    RefreshToken.expires_at > now,
                )
                .values(revoked_at=now)
            ),
        )
        if result.rowcount != 1:
            self._session.rollback()
            raise AuthenticationError("The refresh token is invalid or expired.")
        stored = self._session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        if stored is None:
            raise RuntimeError("Rotated refresh token record was unexpectedly absent.")
        response = self._issue_tokens(user)
        self._session.flush()
        stored.replaced_by_id = self._session.scalar(
            select(RefreshToken.id).where(
                RefreshToken.token_hash == _hash_token(response.refresh_token)
            )
        )
        record_audit(
            self._session,
            action="identity.refresh",
            entity_type="user",
            entity_id=user.id,
            actor_id=user.id,
        )
        self._session.commit()
        return response

    def logout(self, refresh_token: str) -> None:
        """Revoke one valid refresh token."""
        self._jwt.validate_token(refresh_token, expected_type=TokenType.REFRESH)
        token = self._session.scalar(
            select(RefreshToken).where(
                RefreshToken.token_hash == _hash_token(refresh_token)
            )
        )
        if token is not None and token.revoked_at is None:
            token.revoked_at = utc_now()
            record_audit(
                self._session,
                action="identity.logout",
                entity_type="user",
                entity_id=token.user_id,
                actor_id=token.user_id,
            )
            self._session.commit()

    def change_password(
        self, user_id: UUID, current_password: str, new_password: str
    ) -> None:
        """Replace a password after verification and history-reuse checks."""
        user = self._get_user(user_id)
        if not self._passwords.verify_password(current_password, user.password_hash):
            raise AuthenticationError("Current password is incorrect.")
        validate_password_policy(new_password)
        history_hashes = self._session.scalars(
            select(PasswordHistory.password_hash)
            .where(
                PasswordHistory.user_id == user_id,
                PasswordHistory.is_deleted.is_(False),
            )
            .order_by(PasswordHistory.created_at.desc())
            .limit(self._settings.security.password_history_count)
        ).all()
        if any(
            self._passwords.verify_password(new_password, item)
            for item in [user.password_hash, *history_hashes]
        ):
            raise BusinessRuleError("A recent password cannot be reused.")
        self._session.add(
            PasswordHistory(
                user_id=user.id, password_hash=user.password_hash, created_by=user_id
            )
        )
        user.password_hash = self._passwords.hash_password(new_password)
        user.force_password_change = False
        self._revoke_user_tokens(user.id)
        record_audit(
            self._session,
            action="identity.password_changed",
            entity_type="user",
            entity_id=user.id,
            actor_id=user.id,
        )
        self._session.commit()

    def get_user_preferences(self, user_id: UUID) -> UserPreferences:
        """Return a user's preferences, creating the current default document lazily."""
        self._get_user(user_id)
        preferences = self._session.scalar(
            select(UserPreferences).where(
                UserPreferences.user_id == user_id,
                UserPreferences.is_deleted.is_(False),
            )
        )
        if preferences is not None:
            return preferences
        preferences = UserPreferences(
            user_id=user_id,
            created_by=user_id,
            updated_by=user_id,
        )
        self._session.add(preferences)
        try:
            self._session.commit()
        except IntegrityError:
            self._session.rollback()
            preferences = self._session.scalar(
                select(UserPreferences).where(
                    UserPreferences.user_id == user_id,
                    UserPreferences.is_deleted.is_(False),
                )
            )
            if preferences is None:
                raise
        return preferences

    def update_user_preferences(
        self, user_id: UUID, data: UserPreferencesUpdate
    ) -> UserPreferences:
        """Apply a partial update to the authenticated user's preferences."""
        preferences = self.get_user_preferences(user_id)
        changes = data.model_dump(exclude_unset=True)
        if "default_firm_id" in changes and changes["default_firm_id"] is not None:
            firm_id = cast(UUID, changes["default_firm_id"])
            membership = self._session.scalar(
                select(UserFirm.id)
                .join(Firm, Firm.id == UserFirm.firm_id)
                .where(
                    UserFirm.user_id == user_id,
                    UserFirm.firm_id == firm_id,
                    UserFirm.is_active.is_(True),
                    UserFirm.is_deleted.is_(False),
                    Firm.is_active.is_(True),
                    Firm.is_deleted.is_(False),
                )
            )
            if membership is None:
                raise BusinessRuleError(
                    "Default firm must be an active firm membership for this user."
                )
        for field, value in changes.items():
            setattr(preferences, field, value)
        preferences.updated_by = user_id
        record_audit(
            self._session,
            action="user_preferences.updated",
            entity_type="user_preferences",
            entity_id=preferences.id,
            actor_id=user_id,
        )
        self._session.commit()
        return preferences

    def reset_user_preferences(self, user_id: UUID) -> UserPreferences:
        """Replace preferences with the current version's defaults."""
        preferences = self.get_user_preferences(user_id)
        for field, value in {
            "preferences_version": 1,
            "preferred_theme": "light",
            "language": "en",
            "date_format": "yyyy-MM-dd",
            "time_format": "24h",
            "number_format": "1,234.56",
            "currency_format": "symbol",
            "default_firm_id": None,
            "default_landing_page": "dashboard",
            "rows_per_page": 20,
            "notification_preferences": {},
            "dashboard_layout": {},
        }.items():
            setattr(preferences, field, value)
        preferences.updated_by = user_id
        record_audit(
            self._session,
            action="user_preferences.reset",
            entity_type="user_preferences",
            entity_id=preferences.id,
            actor_id=user_id,
        )
        self._session.commit()
        return preferences

    def create_user(
        self, data: UserCreate, actor_id: UUID, firm_scope: UUID | None = None
    ) -> User:
        """Provision a user with a policy-compliant initial password."""
        email = validate_email(data.email)
        if self._session.scalar(select(User.id).where(User.email == email)):
            raise ConflictError("A user with this email already exists.")
        validate_password_policy(data.password)
        user = User(
            email=email,
            full_name=data.full_name.strip(),
            password_hash=self._passwords.hash_password(data.password),
            is_active=data.is_active,
            force_password_change=data.force_password_change,
            expires_at=data.expires_at,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(user)
        self._session.flush()
        if firm_scope is not None:
            self._session.add(
                UserFirm(
                    user_id=user.id,
                    firm_id=firm_scope,
                    is_primary=True,
                    is_active=True,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        record_audit(
            self._session,
            action="user.created",
            entity_type="user",
            entity_id=user.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={"email": user.email},
        )
        self._session.commit()
        return user

    def update_user(
        self,
        user_id: UUID,
        data: UserUpdate,
        actor_id: UUID,
        firm_scope: UUID | None = None,
    ) -> User:
        """Update allowed user properties or explicitly remove a lock."""
        user = self._get_user(user_id, firm_scope)
        if firm_scope is not None:
            self._assert_exclusive_firm_user(user.id, firm_scope)
        before = {"full_name": user.full_name, "is_active": user.is_active}
        if data.full_name is not None:
            user.full_name = data.full_name.strip()
        if data.is_active is not None:
            user.is_active = data.is_active
        if "expires_at" in data.model_fields_set:
            user.expires_at = data.expires_at
        if data.unlock:
            user.locked_until, user.failed_login_attempts = None, 0
        user.updated_by = actor_id
        self._revoke_user_tokens(user.id)
        record_audit(
            self._session,
            action="user.updated",
            entity_type="user",
            entity_id=user.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data=before,
        )
        self._session.commit()
        return user

    def delete_user(
        self, user_id: UUID, actor_id: UUID, firm_scope: UUID | None = None
    ) -> None:
        """Soft delete a non-platform-admin user and revoke all sessions."""
        user = self._get_user(user_id, firm_scope)
        if firm_scope is not None:
            self._assert_exclusive_firm_user(user.id, firm_scope)
        if self._is_platform_admin(user.id):
            raise BusinessRuleError("Platform administrator users cannot be deleted.")
        user.is_deleted = True
        user.deleted_at = utc_now()
        user.deleted_by = actor_id
        user.updated_by = actor_id
        self._revoke_user_tokens(user.id)
        record_audit(
            self._session,
            action="user.deleted",
            entity_type="user",
            entity_id=user.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        self._session.commit()

    def list_users(
        self,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
        firm_scope: UUID | None = None,
    ) -> tuple[list[User], int]:
        """Return a safe, bounded and whitelisted user page."""
        columns = {
            "email": User.email,
            "full_name": User.full_name,
            "created_at": User.created_at,
        }
        statement = select(User).where(User.is_deleted.is_(False))
        count = select(func.count()).select_from(User).where(User.is_deleted.is_(False))
        if firm_scope is not None:
            scoped_users = select(UserFirm.user_id).where(
                UserFirm.firm_id == firm_scope,
                UserFirm.is_active.is_(True),
                UserFirm.is_deleted.is_(False),
            )
            statement = statement.where(
                User.id.in_(scoped_users),
                ~User.id.in_(
                    select(PlatformAdmin.user_id).where(
                        PlatformAdmin.is_deleted.is_(False)
                    )
                ),
            )
            count = count.where(
                User.id.in_(scoped_users),
                ~User.id.in_(
                    select(PlatformAdmin.user_id).where(
                        PlatformAdmin.is_deleted.is_(False)
                    )
                ),
            )
        if search:
            term = f"%{search.strip()}%"
            condition = or_(User.email.ilike(term), User.full_name.ilike(term))
            statement, count = statement.where(condition), count.where(condition)
        ordering = columns[sort_by].desc() if descending else columns[sort_by].asc()
        rows = self._session.scalars(
            statement.order_by(ordering).offset((page - 1) * page_size).limit(page_size)
        ).all()
        return list(rows), int(self._session.scalar(count) or 0)

    def create_role(
        self, data: RoleCreate, actor_id: UUID, firm_scope: UUID | None = None
    ) -> Role:
        """Create a custom role; system classification cannot be client supplied."""
        if self._session.scalar(select(Role.id).where(Role.code == data.code)):
            raise ConflictError("A role with this code already exists.")
        role = Role(
            **data.model_dump(),
            is_system=False,
            firm_id=firm_scope,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(role)
        self._session.flush()
        record_audit(
            self._session,
            action="role.created",
            entity_type="role",
            entity_id=role.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        self._session.commit()
        return role

    def update_role(
        self,
        role_id: UUID,
        data: RoleUpdate,
        actor_id: UUID,
        firm_scope: UUID | None = None,
    ) -> Role:
        """Update a role unless it is system-defined."""
        role = self._get_role(role_id, firm_scope)
        if role.is_system:
            raise BusinessRuleError("System roles cannot be modified.")
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(role, field, value)
        role.updated_by = actor_id
        self._revoke_role_users(role.id)
        record_audit(
            self._session,
            action="role.updated",
            entity_type="role",
            entity_id=role.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        self._session.commit()
        return role

    def delete_role(
        self, role_id: UUID, actor_id: UUID, firm_scope: UUID | None = None
    ) -> None:
        """Soft delete a custom role."""
        role = self._get_role(role_id, firm_scope)
        if role.is_system:
            raise BusinessRuleError("System roles cannot be deleted.")
        role.is_deleted = True
        role.deleted_at = utc_now()
        role.deleted_by = actor_id
        role.updated_by = actor_id
        self._revoke_role_users(role.id)
        record_audit(
            self._session,
            action="role.deleted",
            entity_type="role",
            entity_id=role.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        self._session.commit()

    def list_roles(
        self,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
        firm_scope: UUID | None = None,
    ) -> tuple[list[Role], int]:
        """Return a paginated, searchable role collection."""
        columns = {"code": Role.code, "name": Role.name, "created_at": Role.created_at}
        statement = select(Role).where(
            Role.is_deleted.is_(False),
            Role.code.not_in(HIDDEN_SYSTEM_ROLE_CODES),
        )
        count = (
            select(func.count())
            .select_from(Role)
            .where(
                Role.is_deleted.is_(False),
                Role.code.not_in(HIDDEN_SYSTEM_ROLE_CODES),
            )
        )
        if firm_scope is not None:
            scope_condition = or_(
                Role.firm_id == firm_scope,
                Role.code.in_(FIRM_ROLE_CODES),
            )
            statement = statement.where(scope_condition)
            count = count.where(scope_condition)
        if search:
            condition = or_(
                Role.code.ilike(f"%{search.strip()}%"),
                Role.name.ilike(f"%{search.strip()}%"),
            )
            statement, count = statement.where(condition), count.where(condition)
        ordering = columns[sort_by].desc() if descending else columns[sort_by].asc()
        rows = self._session.scalars(
            statement.order_by(ordering).offset((page - 1) * page_size).limit(page_size)
        )
        return list(rows), int(self._session.scalar(count) or 0)

    def get_role(self, role_id: UUID, firm_scope: UUID | None = None) -> Role:
        """Return one visible role."""
        return self._get_role(role_id, firm_scope)

    def create_permission(self, data: PermissionCreate, actor_id: UUID) -> Permission:
        """Create a permission capability."""
        if self._session.scalar(
            select(Permission.id).where(Permission.code == data.code)
        ):
            raise ConflictError("A permission with this code already exists.")
        permission = Permission(
            **data.model_dump(),
            is_system=False,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(permission)
        self._session.flush()
        record_audit(
            self._session,
            action="permission.created",
            entity_type="permission",
            entity_id=permission.id,
            actor_id=actor_id,
        )
        self._session.commit()
        return permission

    def update_permission(
        self, permission_id: UUID, data: PermissionUpdate, actor_id: UUID
    ) -> Permission:
        """Update a permission capability."""
        permission = self._get_permission(permission_id)
        if permission.is_system:
            raise BusinessRuleError("System permissions cannot be modified.")
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(permission, field, value)
        permission.updated_by = actor_id
        self._revoke_permission_users(permission.id)
        record_audit(
            self._session,
            action="permission.updated",
            entity_type="permission",
            entity_id=permission.id,
            actor_id=actor_id,
        )
        self._session.commit()
        return permission

    def delete_permission(self, permission_id: UUID, actor_id: UUID) -> None:
        """Soft delete a permission not used by active roles."""
        permission = self._get_permission(permission_id)
        if permission.is_system:
            raise BusinessRuleError("System permissions cannot be deleted.")
        assigned = self._session.scalar(
            select(RolePermission.id).where(
                RolePermission.permission_id == permission.id,
                RolePermission.is_deleted.is_(False),
            )
        )
        if assigned is not None:
            raise BusinessRuleError("Assigned permissions cannot be deleted.")
        permission.is_deleted, permission.deleted_at, permission.updated_by = (
            True,
            utc_now(),
            actor_id,
        )
        permission.deleted_by = actor_id
        self._revoke_permission_users(permission.id)
        record_audit(
            self._session,
            action="permission.deleted",
            entity_type="permission",
            entity_id=permission.id,
            actor_id=actor_id,
        )
        self._session.commit()

    def list_permissions(
        self,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
        firm_scope: UUID | None = None,
    ) -> tuple[list[Permission], int]:
        """Return a paginated, searchable permission collection."""
        columns = {
            "code": Permission.code,
            "name": Permission.name,
            "created_at": Permission.created_at,
        }
        statement = select(Permission).where(Permission.is_deleted.is_(False))
        count = (
            select(func.count())
            .select_from(Permission)
            .where(Permission.is_deleted.is_(False))
        )
        if firm_scope is not None:
            statement = statement.where(
                Permission.code.not_in(PLATFORM_PERMISSION_CODES)
            )
            count = count.where(Permission.code.not_in(PLATFORM_PERMISSION_CODES))
        if search:
            condition = or_(
                Permission.code.ilike(f"%{search.strip()}%"),
                Permission.name.ilike(f"%{search.strip()}%"),
            )
            statement, count = statement.where(condition), count.where(condition)
        ordering = columns[sort_by].desc() if descending else columns[sort_by].asc()
        rows = self._session.scalars(
            statement.order_by(ordering).offset((page - 1) * page_size).limit(page_size)
        )
        return list(rows), int(self._session.scalar(count) or 0)

    def get_permission(
        self, permission_id: UUID, firm_scope: UUID | None = None
    ) -> Permission:
        """Return one visible permission."""
        permission = self._get_permission(permission_id)
        if (
            firm_scope is not None
            and permission.code in PLATFORM_PERMISSION_CODES
        ):
            raise ResourceNotFoundError("Permission not found.")
        return permission

    def list_user_role_ids(
        self, user_id: UUID, firm_scope: UUID | None = None
    ) -> list[UUID]:
        """Return role identifiers assigned to one visible user."""
        self._get_user(user_id, firm_scope)
        conditions = [
            UserRole.user_id == user_id,
            UserRole.is_deleted.is_(False),
        ]
        if firm_scope is not None:
            conditions.append(UserRole.firm_id == firm_scope)
        return list(
            self._session.scalars(
                select(UserRole.role_id).where(
                    *conditions
                )
            )
        )

    def list_role_permission_ids(
        self, role_id: UUID, firm_scope: UUID | None = None
    ) -> list[UUID]:
        """Return permission identifiers assigned to one visible role."""
        self._get_role(role_id, firm_scope)
        return list(
            self._session.scalars(
                select(RolePermission.permission_id).where(
                    RolePermission.role_id == role_id,
                    RolePermission.is_deleted.is_(False),
                )
            )
        )

    def set_role_permissions(
        self,
        role_id: UUID,
        permission_ids: list[UUID],
        actor_id: UUID,
        firm_scope: UUID | None = None,
    ) -> None:
        """Replace a role's permission assignment set."""
        role = self._get_role(role_id, firm_scope)
        if role.is_system:
            raise BusinessRuleError("System role assignments cannot be modified.")
        self._ensure_identifiers(Permission, permission_ids)
        if firm_scope is not None:
            forbidden = self._session.scalar(
                select(Permission.id).where(
                    Permission.id.in_(permission_ids),
                    Permission.code.in_(PLATFORM_PERMISSION_CODES),
                )
            )
            if forbidden is not None:
                raise BusinessRuleError(
                    "Platform permissions cannot be assigned to firm roles."
                )
        self._replace_associations(
            RolePermission,
            "role_id",
            role.id,
            "permission_id",
            permission_ids,
            actor_id,
        )
        self._revoke_role_users(role.id)
        record_audit(
            self._session,
            action="role.permissions_set",
            entity_type="role",
            entity_id=role.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        self._session.commit()

    def set_user_roles(
        self,
        user_id: UUID,
        role_ids: list[UUID],
        actor_id: UUID,
        firm_scope: UUID | None = None,
    ) -> None:
        """Replace a user's role assignment set."""
        user = self._get_user(user_id, firm_scope)
        self._ensure_identifiers(Role, role_ids)
        if firm_scope is None:
            self._replace_associations(
                UserRole, "user_id", user.id, "role_id", role_ids, actor_id
            )
        else:
            allowed_count = self._session.scalar(
                select(func.count())
                .select_from(Role)
                .where(
                    Role.id.in_(role_ids),
                    Role.is_deleted.is_(False),
                    or_(
                        Role.firm_id == firm_scope,
                        Role.code.in_(FIRM_ROLE_CODES),
                    ),
                )
            )
            if int(allowed_count or 0) != len(role_ids):
                raise BusinessRuleError(
                    "Platform or cross-firm roles cannot be assigned."
                )
            self._replace_scoped_user_roles(
                user.id, role_ids, actor_id, firm_scope
            )
        self._revoke_user_tokens(user.id)
        record_audit(
            self._session,
            action="user.roles_set",
            entity_type="user",
            entity_id=user.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        self._session.commit()

    def set_user_firms(
        self, user_id: UUID, assignments: list[UserFirmAssignment], actor_id: UUID
    ) -> list[UserFirm]:
        """Replace firm memberships while enforcing a single active primary firm."""
        user = self._get_user_for_update(user_id)
        firm_ids = [item.firm_id for item in assignments]
        if len(firm_ids) != len(set(firm_ids)):
            raise BusinessRuleError("A firm can only be assigned once.")
        if sum(item.is_primary and item.is_active for item in assignments) > 1:
            raise BusinessRuleError("Only one active firm may be primary.")
        self._ensure_identifiers(Firm, firm_ids)
        existing_by_firm = {
            item.firm_id: item
            for item in self._session.scalars(
                select(UserFirm).where(UserFirm.user_id == user.id).with_for_update()
            )
        }
        requested_firm_ids = set(firm_ids)
        requested_primary_firm_ids = {
            item.firm_id for item in assignments if item.is_active and item.is_primary
        }
        current_primary_firm_ids = {
            firm_id
            for firm_id, item in existing_by_firm.items()
            if not item.is_deleted and item.is_active and item.is_primary
        }
        if requested_primary_firm_ids != current_primary_firm_ids:
            for item in existing_by_firm.values():
                if not item.is_deleted and item.is_active and item.is_primary:
                    item.is_primary = False
                    item.updated_by = actor_id
            self._session.flush()
        now = utc_now()
        result: list[UserFirm] = []
        for assignment in assignments:
            existing = existing_by_firm.get(assignment.firm_id)
            if existing is None:
                existing = UserFirm(
                    user_id=user.id,
                    firm_id=assignment.firm_id,
                    is_primary=assignment.is_primary,
                    is_active=assignment.is_active,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
                self._session.add(existing)
            elif (
                existing.is_deleted
                or existing.is_primary != assignment.is_primary
                or existing.is_active != assignment.is_active
            ):
                existing.is_deleted = False
                existing.deleted_at = None
                existing.deleted_by = None
                existing.is_primary = assignment.is_primary
                existing.is_active = assignment.is_active
                existing.updated_by = actor_id
            result.append(existing)
        for firm_id, existing in existing_by_firm.items():
            if not existing.is_deleted and firm_id not in requested_firm_ids:
                existing.is_deleted = True
                existing.deleted_at = now
                existing.deleted_by = actor_id
                existing.updated_by = actor_id
        record_audit(
            self._session,
            action="user.firms_set",
            entity_type="user",
            entity_id=user.id,
            actor_id=actor_id,
        )
        self._revoke_user_tokens(user.id)
        self._session.commit()
        return result

    def list_user_firms(self, user_id: UUID) -> list[UserFirm]:
        """Return visible firm memberships for one visible user."""
        self._get_user(user_id)
        return list(
            self._session.scalars(
                select(UserFirm).where(
                    UserFirm.user_id == user_id, UserFirm.is_deleted.is_(False)
                )
            )
        )

    def list_my_firms(self, user_id: UUID) -> list[tuple[UserFirm, Firm]]:
        """Return active firms assigned to the authenticated user."""
        self._get_user(user_id)
        rows = self._session.execute(
            select(UserFirm, Firm)
            .join(Firm, Firm.id == UserFirm.firm_id)
            .where(
                UserFirm.user_id == user_id,
                UserFirm.is_active.is_(True),
                UserFirm.is_deleted.is_(False),
                Firm.is_active.is_(True),
                Firm.is_deleted.is_(False),
            )
            .order_by(UserFirm.is_primary.desc(), Firm.name.asc())
        )
        return [(row[0], row[1]) for row in rows]

    def _issue_tokens(self, user: User) -> TokenResponse:
        roles = list(
            self._session.scalars(
                select(Role.code)
                .join(UserRole)
                .where(
                    UserRole.user_id == user.id,
                    UserRole.is_deleted.is_(False),
                    Role.is_deleted.is_(False),
                    Role.is_active.is_(True),
                )
            )
        )
        is_platform_admin = self._is_platform_admin(user.id)
        if is_platform_admin:
            roles.append("platform_admin")
        if is_platform_admin:
            permissions = list(
                self._session.scalars(
                    select(Permission.code).where(
                        Permission.is_deleted.is_(False),
                        Permission.is_active.is_(True),
                    )
                )
            )
        else:
            permissions = list(
                self._session.scalars(
                    select(Permission.code)
                    .join(RolePermission)
                    .join(Role, Role.id == RolePermission.role_id)
                    .join(UserRole, UserRole.role_id == RolePermission.role_id)
                    .where(
                        UserRole.user_id == user.id,
                        UserRole.firm_id.is_(None),
                        UserRole.is_deleted.is_(False),
                        RolePermission.is_deleted.is_(False),
                        Role.is_deleted.is_(False),
                        Role.is_active.is_(True),
                        Permission.is_deleted.is_(False),
                        Permission.is_active.is_(True),
                        or_(
                            Role.code.in_(PLATFORM_ROLE_CODES),
                            Role.is_system.is_(False),
                        ),
                    )
                    .distinct()
                )
            )
        firm_permissions: dict[str, list[str]] = {}
        if not is_platform_admin:
            memberships = list(
                self._session.scalars(
                    select(UserFirm.firm_id).where(
                        UserFirm.user_id == user.id,
                        UserFirm.is_active.is_(True),
                        UserFirm.is_deleted.is_(False),
                    )
                )
            )
            for firm_id in memberships:
                firm_permissions[str(firm_id)] = list(
                    self._session.scalars(
                        select(Permission.code)
                        .join(RolePermission)
                        .join(Role, Role.id == RolePermission.role_id)
                        .join(UserRole, UserRole.role_id == RolePermission.role_id)
                        .where(
                            UserRole.user_id == user.id,
                            or_(
                                UserRole.firm_id == firm_id,
                                (
                                    UserRole.firm_id.is_(None)
                                    & Role.code.in_(FIRM_ROLE_CODES)
                                ),
                            ),
                            UserRole.is_deleted.is_(False),
                            RolePermission.is_deleted.is_(False),
                            Role.is_deleted.is_(False),
                            Role.is_active.is_(True),
                            Permission.is_deleted.is_(False),
                            Permission.is_active.is_(True),
                        )
                        .distinct()
                    )
                )
        claims = {
            "roles": roles,
            "permissions": permissions,
            "firm_permissions": firm_permissions,
            "authorization_version": user.authorization_version,
            "password_change_required": user.force_password_change,
        }
        access = self._jwt.generate_access_token(user.id, claims=claims)
        refresh = self._jwt.generate_refresh_token(user.id)
        expiry = datetime.fromtimestamp(
            self._jwt.validate_token(
                refresh, expected_type=TokenType.REFRESH
            ).expires_at,
            UTC,
        )
        self._session.add(
            RefreshToken(
                user_id=user.id, token_hash=_hash_token(refresh), expires_at=expiry
            )
        )
        return TokenResponse(
            access_token=access,
            refresh_token=refresh,
            must_change_password=user.force_password_change,
        )

    def _register_failed_login(
        self, user: User, client_ip: str | None, user_agent: str | None
    ) -> None:
        user.failed_login_attempts += 1
        outcome = "failed"
        if user.failed_login_attempts >= self._settings.security.max_login_attempts:
            user.locked_until = utc_now() + timedelta(
                minutes=self._settings.security.lockout_minutes
            )
            outcome = "locked"
        self._record_login(
            user.id, user.email, outcome, client_ip, user_agent, "invalid_credentials"
        )
        self._session.commit()

    def _record_login(
        self,
        user_id: UUID | None,
        email: str,
        outcome: str,
        client_ip: str | None,
        user_agent: str | None,
        reason: str | None,
    ) -> None:
        self._session.add(
            LoginHistory(
                user_id=user_id,
                attempted_email=email,
                outcome=outcome,
                client_ip=client_ip,
                user_agent=user_agent,
                failure_reason=reason,
            )
        )

    def _revoke_user_tokens(self, user_id: UUID) -> None:
        user = self._session.get(User, user_id)
        if user is not None:
            user.authorization_version += 1
        now = utc_now()
        for token in self._session.scalars(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
            )
        ):
            token.revoked_at = now

    def _revoke_role_users(self, role_id: UUID) -> None:
        user_ids = self._session.scalars(
            select(UserRole.user_id).where(
                UserRole.role_id == role_id,
                UserRole.is_deleted.is_(False),
            )
        ).all()
        for user_id in set(user_ids):
            self._revoke_user_tokens(user_id)

    def _revoke_permission_users(self, permission_id: UUID) -> None:
        role_ids = self._session.scalars(
            select(RolePermission.role_id).where(
                RolePermission.permission_id == permission_id,
                RolePermission.is_deleted.is_(False),
            )
        ).all()
        for role_id in set(role_ids):
            self._revoke_role_users(role_id)

    def _get_user(
        self, user_id: UUID, firm_scope: UUID | None = None
    ) -> User:
        statement = select(User).where(
            User.id == user_id, User.is_deleted.is_(False)
        )
        if firm_scope is not None:
            statement = statement.where(
                User.id.in_(
                    select(UserFirm.user_id).where(
                        UserFirm.firm_id == firm_scope,
                        UserFirm.is_active.is_(True),
                        UserFirm.is_deleted.is_(False),
                    )
                ),
                ~User.id.in_(
                    select(PlatformAdmin.user_id).where(
                        PlatformAdmin.is_deleted.is_(False)
                    )
                ),
            )
        user = self._session.scalar(statement)
        if user is None:
            raise ResourceNotFoundError("User not found.")
        return user

    def _get_user_for_update(self, user_id: UUID) -> User:
        """Lock a user row to serialize its firm-membership replacements."""
        user = self._session.scalar(
            select(User)
            .where(User.id == user_id, User.is_deleted.is_(False))
            .with_for_update()
        )
        if user is None:
            raise ResourceNotFoundError("User not found.")
        return user

    def _assert_exclusive_firm_user(self, user_id: UUID, firm_id: UUID) -> None:
        other_membership = self._session.scalar(
            select(UserFirm.id).where(
                UserFirm.user_id == user_id,
                UserFirm.firm_id != firm_id,
                UserFirm.is_active.is_(True),
                UserFirm.is_deleted.is_(False),
            )
        )
        if other_membership is not None:
            raise BusinessRuleError(
                "Users assigned to multiple firms require platform administration."
            )

    def _get_role(
        self, role_id: UUID, firm_scope: UUID | None = None
    ) -> Role:
        statement = select(Role).where(
            Role.id == role_id, Role.is_deleted.is_(False)
        )
        if firm_scope is not None:
            statement = statement.where(
                or_(Role.firm_id == firm_scope, Role.code.in_(FIRM_ROLE_CODES))
            )
        role = self._session.scalar(statement)
        if role is None:
            raise ResourceNotFoundError("Role not found.")
        return role

    def _get_permission(self, permission_id: UUID) -> Permission:
        permission = self._session.scalar(
            select(Permission).where(
                Permission.id == permission_id, Permission.is_deleted.is_(False)
            )
        )
        if permission is None:
            raise ResourceNotFoundError("Permission not found.")
        return permission

    def _ensure_identifiers(
        self, model: type[Role] | type[Permission] | type[Firm], identifiers: list[UUID]
    ) -> None:
        if len(identifiers) != len(set(identifiers)):
            raise BusinessRuleError("Duplicate identifiers are not allowed.")
        if not identifiers:
            return
        count = self._session.scalar(
            select(func.count())
            .select_from(model)
            .where(model.id.in_(identifiers), model.is_deleted.is_(False))
        )
        if int(count or 0) != len(identifiers):
            raise ResourceNotFoundError(
                "One or more referenced resources were not found."
            )

    def _replace_associations(
        self,
        model: type[RolePermission] | type[UserRole],
        owner_field: str,
        owner_id: UUID,
        related_field: str,
        related_ids: list[UUID],
        actor_id: UUID,
    ) -> None:
        existing_by_related_id = {
            getattr(item, related_field): item
            for item in self._session.scalars(
                select(model).where(getattr(model, owner_field) == owner_id)
            )
        }
        requested_related_ids = set(related_ids)
        now = utc_now()
        for related_id in related_ids:
            existing = existing_by_related_id.get(related_id)
            if existing is None:
                self._session.add(
                    model(
                        **{owner_field: owner_id, related_field: related_id},
                        created_by=actor_id,
                        updated_by=actor_id,
                    )
                )
            elif existing.is_deleted:
                existing.is_deleted = False
                existing.deleted_at = None
                existing.deleted_by = None
                existing.updated_by = actor_id
        for related_id, existing in existing_by_related_id.items():
            if not existing.is_deleted and related_id not in requested_related_ids:
                existing.is_deleted = True
                existing.deleted_at = now
                existing.deleted_by = actor_id
                existing.updated_by = actor_id

    def _replace_scoped_user_roles(
        self,
        user_id: UUID,
        role_ids: list[UUID],
        actor_id: UUID,
        firm_id: UUID,
    ) -> None:
        existing_by_role = {
            item.role_id: item
            for item in self._session.scalars(
                select(UserRole).where(
                    UserRole.user_id == user_id,
                    UserRole.firm_id == firm_id,
                )
            )
        }
        requested = set(role_ids)
        now = utc_now()
        for role_id in role_ids:
            existing = existing_by_role.get(role_id)
            if existing is None:
                self._session.add(
                    UserRole(
                        user_id=user_id,
                        role_id=role_id,
                        firm_id=firm_id,
                        created_by=actor_id,
                        updated_by=actor_id,
                    )
                )
            elif existing.is_deleted:
                existing.is_deleted = False
                existing.deleted_at = None
                existing.deleted_by = None
                existing.updated_by = actor_id
        for role_id, existing in existing_by_role.items():
            if not existing.is_deleted and role_id not in requested:
                existing.is_deleted = True
                existing.deleted_at = now
                existing.deleted_by = actor_id
                existing.updated_by = actor_id
    def _is_platform_admin(self, user_id: UUID) -> bool:
        return (
            self._session.scalar(
                select(PlatformAdmin.id).where(
                    PlatformAdmin.user_id == user_id,
                    PlatformAdmin.is_deleted.is_(False),
                )
            )
            is not None
        )


def _hash_token(token: str) -> str:
    """Hash a bearer refresh token before persistence lookup."""
    return sha256(token.encode("utf-8")).hexdigest()
