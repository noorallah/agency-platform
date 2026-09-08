"""Application services for authentication and platform identity administration."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.common.audit.services import record_audit
from app.core.config.settings import Settings
from app.core.enums import PlatformAdminScope, TokenType
from app.core.exceptions import (
    AuthenticationError,
    BusinessRuleError,
    ConflictError,
    ResourceNotFoundError,
    ValidationError,
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
    UserTemplate,
    UserTemplateRole,
)
from app.identity.schemas.api import (
    PermissionCreate,
    PermissionUpdate,
    RoleCreate,
    RoleUpdate,
    TokenResponse,
    UserCloneRequest,
    UserCreate,
    UserFirmAssignment,
    UserPreferencesUpdate,
    UserTemplateCreate,
    UserTemplateUpdate,
    UserUpdate,
)
from app.identity.system_seed import (
    FIRM_ROLE_CODES,
    HIDDEN_SYSTEM_ROLE_CODES,
    PLATFORM_OPERATOR_PERMISSION_CODES,
    PLATFORM_PERMISSION_CODES,
    PLATFORM_ROLE_CODES,
    SYSTEM_ROLE_CODES,
)

_PROFILE_FIELDS = (
    "personal_mobile",
    "alternate_mobile",
    "personal_email",
    "office_email",
    "emergency_contact_name",
    "emergency_mobile",
    "emergency_relationship",
    "employee_code",
    "joining_date",
    "leaving_date",
    "department",
    "designation",
    "reporting_manager",
    "employment_type",
    "cost_center",
    "profile_photo_url",
    "profile_addresses",
    "profile_documents",
)
"""The optional HR/profile columns, written by both create and update.

One list because two lists drift: creation carried none of these at all, so a
mobile number typed into the create form was dropped and the record opened
blank afterwards.
"""


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
            # Verify against a throwaway hash so an unknown address costs the same
            # as a known one. Without this the Argon2 work factor makes the two
            # cases trivially distinguishable by response time, which turns an
            # otherwise-uniform error message into a user-enumeration oracle.
            self._passwords.verify_password(password, _DUMMY_PASSWORD_HASH)
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
            self._handle_refresh_reuse(token_hash, user_id=user.id)
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
            # Which rows fall inside the reuse window must not be arbitrary:
            # created_at is shared by everything one request wrote.
            .order_by(
                PasswordHistory.created_at.desc(),
                PasswordHistory.id.desc(),
            )
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
            "preferred_theme_mode": "system",
            "preferred_high_contrast": False,
            "preferred_palette": "neutral",
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
        # Only live accounts hold an address; soft-deleted users release theirs so
        # a leaver can be re-onboarded. This mirrors UQ_users_email_active and is
        # the authoritative check on backends without partial indexes.
        if self._session.scalar(
            select(User.id).where(User.email == email, User.is_deleted.is_(False))
        ):
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
        # The profile fields are optional and default to None, so an omitted
        # one writes the same value the column would have had anyway.
        for field in _PROFILE_FIELDS:
            setattr(user, field, getattr(data, field))
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
        for field in _PROFILE_FIELDS:
            if field in data.model_fields_set:
                setattr(user, field, getattr(data, field))
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

    def restore_user(self, user_id: UUID, actor_id: UUID) -> User:
        """Bring a soft-deleted user back, with everything they had.

        Deletion marks the row and revokes the sessions; it leaves the firm
        memberships, the roles and the preferences in place. So a restore is
        the one flag, and the person signs in with their old password to their
        old firms and roles. A platform administrator's action, because the
        row is platform-wide and a firm's grid cannot even see a deleted user.

        Refused when a live account has since taken the address: the email is
        unique among live accounts, and two of them cannot coexist. Deciding
        which of the two accounts should survive is a person's call, not this
        method's, so it says why rather than merging anything.
        """
        user = self._session.scalar(select(User).where(User.id == user_id))
        if user is None:
            raise ResourceNotFoundError("User not found.")
        if not user.is_deleted:
            raise BusinessRuleError("This user is not deleted.")
        taken = self._session.scalar(
            select(User.id).where(User.email == user.email, User.is_deleted.is_(False))
        )
        if taken is not None:
            raise BusinessRuleError(
                "Another live account now holds this email address. Delete "
                "that account first if this is the one to keep."
            )
        user.is_deleted = False
        user.deleted_at = None
        user.deleted_by = None
        user.updated_by = actor_id
        record_audit(
            self._session,
            action="user.restored",
            entity_type="user",
            entity_id=user.id,
            actor_id=actor_id,
        )
        self._session.commit()
        return user

    def list_users(
        self,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
        firm_scope: UUID | None = None,
        *,
        deleted_only: bool = False,
    ) -> tuple[list[User], int]:
        """Return a safe, bounded and whitelisted user page.

        `deleted_only` is a platform administrator's switch: a deleted user
        has to be found before it can be restored, and the grid is the only
        place to find one. It answers the deleted rows **instead of** the live
        ones -- the question is "who is deleted", not "everybody, with the
        deleted mixed in". A firm caller never gets it -- the router does not
        pass it for them -- because a deleted person's memberships still stand
        and would place them in a firm they have, in every other sense, left.
        """
        columns = {
            "email": User.email,
            "full_name": User.full_name,
            "created_at": User.created_at,
        }
        statement = select(User).where(User.is_deleted.is_(deleted_only))
        count = (
            select(func.count())
            .select_from(User)
            .where(User.is_deleted.is_(deleted_only))
        )
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
        self._assert_code_is_not_reserved(data.code)
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

    def clone_user(
        self,
        source_id: UUID,
        data: UserCloneRequest,
        actor_id: UUID,
        firm_scope: UUID | None = None,
    ) -> User:
        """Hire somebody to do what an existing person does.

        A template is a job somebody wrote down; this is the job somebody is
        already doing, which is the more common thing an administrator has to
        hand. Both end in an ordinary role set they may edit.

        **Only access is copied.** The new user is built from scratch and given
        the source's roles and firm memberships; every personal thing --
        mobile, employee code, joining date, photo, password, login history,
        password history, audit trail -- is not copied, because it belongs to
        the person rather than the job. That is the whole reason this is not
        "duplicate the row": a row copy carries all of it, and carries it
        silently.

        **The platform designation is never copied.** It lives in
        `platform_admins` and is deliberately unreachable from anything a role
        can express; cloning a platform administrator gives you their roles and
        not their designation, or this method would be a way to mint one.

        Args:
            source_id: The person whose access to copy.
            data: The new person's own details.
            actor_id: Who is doing the hiring.
            firm_scope: The caller's firm, or None for a platform caller.

        Returns:
            The new user.

        """
        target = self._target_firm(firm_scope, data.firm_id)
        source = self._get_user(source_id, target)
        clone = self.create_user(
            UserCreate(
                email=data.email,
                full_name=data.full_name,
                password=data.password,
                is_active=True,
                # A password somebody else chose is not a password. The clone
                # picks their own on first sign-in.
                force_password_change=True,
            ),
            actor_id,
            target,
        )
        role_ids = self._roles_held_by(source.id, target)
        if role_ids:
            self.set_user_roles(clone.id, role_ids, actor_id, target)
        # A platform caller is not creating inside any firm, so the clone would
        # otherwise land nowhere. Copy where the source works.
        if target is None:
            self._copy_memberships(source.id, clone.id, actor_id)
        record_audit(
            self._session,
            action="user.cloned",
            entity_type="user",
            entity_id=clone.id,
            actor_id=actor_id,
            firm_id=target,
            # Which person's access this copied. Without it the trail says a
            # user was created and nothing about where their access came
            # from, which is the one question anybody reviewing it will ask.
            after_data={"source_user_id": str(source.id)},
        )
        self._session.commit()
        return clone

    def _roles_held_by(self, user_id: UUID, firm_scope: UUID | None) -> list[UUID]:
        """Return the roles a user holds, as the given scope sees them.

        A firm caller copies what the source holds **in their firm** -- the
        firm-scoped rows plus the unscoped firm roles that reach every firm.
        Anything belonging to another firm is invisible to them and stays that
        way. A platform caller copies every role the source holds.
        """
        conditions = [
            UserRole.user_id == user_id,
            UserRole.is_deleted.is_(False),
            Role.is_deleted.is_(False),
            Role.is_active.is_(True),
        ]
        if firm_scope is not None:
            conditions.append(
                or_(
                    UserRole.firm_id == firm_scope,
                    and_(
                        UserRole.firm_id.is_(None),
                        Role.code.in_(FIRM_ROLE_CODES),
                    ),
                )
            )
        return list(
            self._session.scalars(
                select(UserRole.role_id)
                .join(Role, Role.id == UserRole.role_id)
                .where(*conditions)
                .distinct()
            )
        )

    def _copy_memberships(
        self, source_id: UUID, clone_id: UUID, actor_id: UUID
    ) -> None:
        """Put the clone in the same firms as the source.

        `is_primary` is not copied: it is a preference about where somebody
        lands when they sign in, and the first membership is as good an answer
        for a new person as any. Copying it would also collide with
        `UQ_user_firms_active_primary` if the source had none.
        """
        memberships = list(
            self._session.scalars(
                select(UserFirm).where(
                    UserFirm.user_id == source_id,
                    UserFirm.is_active.is_(True),
                    UserFirm.is_deleted.is_(False),
                )
            )
        )
        for index, membership in enumerate(memberships):
            self._session.add(
                UserFirm(
                    user_id=clone_id,
                    firm_id=membership.firm_id,
                    is_primary=index == 0,
                    is_active=True,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        self._session.flush()

    # ------------------------------------------------------------------
    # User templates -- a named bundle of roles for one job
    # ------------------------------------------------------------------

    def list_user_templates(
        self,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
        firm_scope: UUID | None = None,
    ) -> tuple[list[UserTemplate], int]:
        """Return the templates this caller may offer, paginated.

        A firm sees the platform's templates **and** its own. A platform caller
        sees every template, which is what makes a support conversation about
        "the template we built for FOOD01" possible at all.
        """
        columns = {
            "code": UserTemplate.code,
            "name": UserTemplate.name,
            "created_at": UserTemplate.created_at,
        }
        conditions: list[ColumnElement[bool]] = [UserTemplate.is_deleted.is_(False)]
        if firm_scope is not None:
            conditions.append(
                or_(
                    UserTemplate.firm_id == firm_scope,
                    UserTemplate.firm_id.is_(None),
                )
            )
        if search:
            needle = f"%{search.strip()}%"
            conditions.append(
                or_(UserTemplate.code.ilike(needle), UserTemplate.name.ilike(needle))
            )
        statement = select(UserTemplate).where(*conditions)
        count = select(func.count()).select_from(UserTemplate).where(*conditions)
        ordering = columns[sort_by].desc() if descending else columns[sort_by].asc()
        rows = list(
            self._session.scalars(
                statement.order_by(ordering)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return rows, int(self._session.scalar(count) or 0)

    def get_user_template(
        self, template_id: UUID, firm_scope: UUID | None = None
    ) -> UserTemplate:
        """Return one visible template."""
        return self._get_user_template(template_id, firm_scope)

    def create_user_template(
        self,
        data: UserTemplateCreate,
        actor_id: UUID,
        firm_scope: UUID | None = None,
    ) -> UserTemplate:
        """Create a template, refusing a bundle its own scope could not apply.

        The roles are validated **here** rather than only at apply time. A
        template naming a role the firm cannot assign is one that fails on
        whoever tries to use it, weeks later, with nothing on screen to say the
        template was wrong rather than their permissions.

        Raises:
            ConflictError: If the code is already taken in this scope.

        """
        owner = self._target_firm(firm_scope, data.firm_id)
        code = data.code.strip().lower()
        if self._user_template_code_taken(code, owner):
            raise ConflictError("A template with this code already exists.")
        # Against the firm that will own it, not the caller's scope. A
        # platform operator writing a template for one firm must not be able
        # to bundle a role that firm could never assign.
        self._assert_roles_are_assignable(data.role_ids, owner)
        template = UserTemplate(
            code=code,
            name=data.name,
            description=data.description,
            is_active=data.is_active,
            firm_id=owner,
            is_system=False,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(template)
        self._session.flush()
        self._set_template_roles(template, data.role_ids, actor_id)
        record_audit(
            self._session,
            action="user_template.created",
            entity_type="user_template",
            entity_id=template.id,
            actor_id=actor_id,
            firm_id=owner,
        )
        self._session.commit()
        return template

    def update_user_template(
        self,
        template_id: UUID,
        data: UserTemplateUpdate,
        actor_id: UUID,
        firm_scope: UUID | None = None,
    ) -> UserTemplate:
        """Update a template.

        Dumps with `exclude_unset=True`, so an omitted field is left alone and
        an explicit null still clears. `role_ids` **replaces** the bundle, and
        that is only safe because the two are distinguishable.

        Raises:
            BusinessRuleError: If the template is platform-provided.

        """
        template = self._get_user_template(template_id, firm_scope)
        if template.is_system:
            raise BusinessRuleError("Platform templates cannot be edited.")
        values = data.model_dump(exclude_unset=True)
        role_ids = values.pop("role_ids", None)
        for field, value in values.items():
            setattr(template, field, value)
        if role_ids is not None:
            self._assert_roles_are_assignable(role_ids, firm_scope)
            self._set_template_roles(template, role_ids, actor_id)
        template.updated_by = actor_id
        record_audit(
            self._session,
            action="user_template.updated",
            entity_type="user_template",
            entity_id=template.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        self._session.commit()
        return template

    def delete_user_template(
        self, template_id: UUID, actor_id: UUID, firm_scope: UUID | None = None
    ) -> None:
        """Soft delete a template.

        Nothing is taken away from anybody: a template is where a user started,
        not something they stay inside, so retiring one leaves every user it
        ever created exactly as they are.

        Raises:
            BusinessRuleError: If the template is platform-provided.

        """
        template = self._get_user_template(template_id, firm_scope)
        if template.is_system:
            raise BusinessRuleError("Platform templates cannot be deleted.")
        template.is_deleted = True
        template.deleted_at = utc_now()
        template.deleted_by = actor_id
        template.updated_by = actor_id
        record_audit(
            self._session,
            action="user_template.deleted",
            entity_type="user_template",
            entity_id=template.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        self._session.commit()

    def apply_user_template(
        self,
        user_id: UUID,
        template_id: UUID,
        actor_id: UUID,
        firm_scope: UUID | None = None,
        firm_id: UUID | None = None,
    ) -> list[UUID]:
        """Give a user the roles a template bundles, and return them.

        A plain `set_user_roles`, deliberately: the template decides where the
        administrator **starts**, and everything after that is an ordinary role
        edit on an ordinary user. Nothing records that a template was used --
        the audit row does, and the user does not, because a user who has since
        been edited is no longer described by the template they came from.

        Raises:
            BusinessRuleError: If the template is inactive.

        """
        target = self._target_firm(firm_scope, firm_id)
        template = self._get_user_template(template_id, target)
        if not template.is_active:
            raise BusinessRuleError("This template is no longer offered.")
        role_ids = [
            row.role_id for row in template.template_roles if not row.is_deleted
        ]
        # Through the ordinary path, so the firm-scope check that refuses a
        # platform or cross-firm role applies here too and there is one
        # implementation of it rather than two.
        self.set_user_roles(user_id, role_ids, actor_id, target)
        record_audit(
            self._session,
            action="user_template.applied",
            entity_type="user",
            entity_id=user_id,
            actor_id=actor_id,
            firm_id=target,
            # Which job, not merely that a job was applied. This recorded
            # neither the template nor the roles, so the trail said somebody's
            # access changed and nothing about what it changed to -- and this
            # is the call a promotion is made with, where "moved into Sales
            # Manager, by whom, on what date" is the whole question somebody
            # asks six months later. `clone_user` already recorded its source
            # for the same reason.
            #
            # The code as well as the id: a template can be retired, and an
            # id alone then points at a row nobody can name.
            after_data={
                "template_id": str(template.id),
                "template_code": template.code,
                "role_ids": [str(role_id) for role_id in role_ids],
            },
        )
        self._session.commit()
        return role_ids

    def _target_firm(self, firm_scope: UUID | None, named: UUID | None) -> UUID | None:
        """Resolve which firm a request is about.

        A firm-scoped caller gets their own firm whatever they send: naming a
        different one is refused rather than ignored, because silently writing
        it somewhere else is how the business-profile assignments came to
        report success while changing nothing.

        A platform caller gets the firm they named. Naming none keeps what a
        platform caller has always meant -- platform-wide for a template,
        global for a role assignment -- so nothing that worked before changes.

        Args:
            firm_scope: The caller's own scope, or None for a platform caller.
            named: The firm named on the request.

        Returns:
            The firm to act in, or None for platform-wide.

        Raises:
            BusinessRuleError: If a firm caller named a different firm.

        """
        if firm_scope is None:
            if named is not None:
                self._ensure_identifiers(Firm, [named])
            return named
        if named is not None and named != firm_scope:
            raise BusinessRuleError("You can only act within your own firm.")
        return firm_scope

    def _get_user_template(
        self, template_id: UUID, firm_scope: UUID | None = None
    ) -> UserTemplate:
        """Return a visible template.

        Raises:
            NotFoundError: If it does not exist or is out of this caller's scope.

        """
        conditions: list[ColumnElement[bool]] = [
            UserTemplate.id == template_id,
            UserTemplate.is_deleted.is_(False),
        ]
        if firm_scope is not None:
            conditions.append(
                or_(
                    UserTemplate.firm_id == firm_scope,
                    UserTemplate.firm_id.is_(None),
                )
            )
        template = self._session.scalar(select(UserTemplate).where(*conditions))
        if template is None:
            raise ResourceNotFoundError("The template was not found.")
        return template

    def _user_template_code_taken(self, code: str, firm_scope: UUID | None) -> bool:
        """Return whether a live template in this scope already holds the code."""
        scope = (
            UserTemplate.firm_id.is_(None)
            if firm_scope is None
            else UserTemplate.firm_id == firm_scope
        )
        return (
            self._session.scalar(
                select(UserTemplate.id).where(
                    UserTemplate.code == code,
                    UserTemplate.is_deleted.is_(False),
                    scope,
                )
            )
            is not None
        )

    def _assert_roles_are_assignable(
        self, role_ids: list[UUID], firm_scope: UUID | None
    ) -> None:
        """Refuse a bundle naming a role this scope could never apply.

        The same condition `set_user_roles` enforces. A firm's template must
        not be able to name `PLATFORM_ADMIN`: that role carries every seeded
        permission code, so bundling it would hand a firm administrator the
        whole catalogue in their own firm through a template rather than
        through a role assignment.

        Raises:
            BusinessRuleError: If any role is out of scope.

        """
        self._ensure_identifiers(Role, role_ids)
        if firm_scope is None:
            return
        allowed = self._session.scalar(
            select(func.count())
            .select_from(Role)
            .where(
                Role.id.in_(role_ids),
                Role.is_deleted.is_(False),
                or_(Role.firm_id == firm_scope, Role.code.in_(FIRM_ROLE_CODES)),
            )
        )
        if int(allowed or 0) != len(set(role_ids)):
            raise BusinessRuleError(
                "A template cannot bundle platform or cross-firm roles."
            )

    def _set_template_roles(
        self, template: UserTemplate, role_ids: list[UUID], actor_id: UUID
    ) -> None:
        """Replace a template's bundle."""
        wanted = list(dict.fromkeys(role_ids))
        existing = {row.role_id: row for row in template.template_roles}
        for role_id, row in existing.items():
            row.is_deleted = role_id not in wanted
            if row.is_deleted:
                row.deleted_at = utc_now()
                row.deleted_by = actor_id
            else:
                row.deleted_at, row.deleted_by = None, None
            row.updated_by = actor_id
        for role_id in wanted:
            if role_id not in existing:
                template.template_roles.append(
                    UserTemplateRole(
                        role_id=role_id, created_by=actor_id, updated_by=actor_id
                    )
                )
        self._session.flush()

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
        if firm_scope is not None and permission.code in PLATFORM_PERMISSION_CODES:
            raise ResourceNotFoundError("Permission not found.")
        return permission

    def list_user_role_ids(
        self, user_id: UUID, firm_scope: UUID | None = None
    ) -> list[UUID]:
        """Return role identifiers assigned to one visible user."""
        # A platform caller may read a deleted user's roles: the view dialog
        # on a deleted row reads them, and they are part of what a restore
        # brings back.
        self._get_user(user_id, firm_scope, include_deleted=firm_scope is None)
        # What the caller sees is what the caller manages. A platform caller
        # reads the **global** set, because that is what their save replaces;
        # returning every row from every firm merged into one list made the
        # screen read as "holds all of these, everywhere" and invited a save
        # that made it true.
        scope = (
            UserRole.firm_id.is_(None)
            if firm_scope is None
            else UserRole.firm_id == firm_scope
        )
        return list(
            self._session.scalars(
                select(UserRole.role_id).where(
                    UserRole.user_id == user_id,
                    UserRole.is_deleted.is_(False),
                    scope,
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
            # The **global** set: `firm_id IS NULL`, which applies in every
            # firm the person belongs to. Only a platform administrator writes
            # these, and a firm administrator can neither edit nor remove one.
            #
            # It replaces the global rows and nothing else. `_replace_associations`
            # keys on `role_id` alone and would soft-delete every firm-scoped
            # row as well, then re-create the survivors unscoped -- so a
            # platform administrator opening this and pressing Save, changing
            # nothing, collapsed each firm's own roles into global ones.
            self._replace_global_user_roles(user.id, role_ids, actor_id)
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
            self._replace_scoped_user_roles(user.id, role_ids, actor_id, firm_scope)
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
        self,
        user_id: UUID,
        assignments: list[UserFirmAssignment],
        actor_id: UUID,
        allowed_firm_ids: frozenset[UUID] | None = None,
    ) -> list[UserFirm]:
        """Replace firm memberships while enforcing a single active primary firm.

        `allowed_firm_ids` is the reach of the caller: the firms they may put
        people into. None means every firm, which is what a platform
        administrator has always had, so their behaviour is unchanged.

        For anybody else this **merges rather than replaces**. The method's own
        last loop soft-deletes every membership the request did not name, which
        is right when the caller can see them all and destructive when they
        cannot: a firm administrator saving a user's membership of their own
        firm would otherwise silently remove that person from every other firm
        on the platform. Memberships outside the caller's reach are carried
        through untouched, so what they save is what they could see.

        Args:
            user_id: The person whose memberships to set.
            assignments: The memberships being asked for.
            actor_id: Who is asking.
            allowed_firm_ids: The firms the caller may staff, or None for all.

        Returns:
            The resulting memberships.

        """
        user = self._get_user_for_update(user_id)
        if allowed_firm_ids is not None:
            assignments = self._merged_within_reach(
                user.id, assignments, allowed_firm_ids
            )
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

    def _merged_within_reach(
        self,
        user_id: UUID,
        assignments: list[UserFirmAssignment],
        allowed_firm_ids: frozenset[UUID],
    ) -> list[UserFirmAssignment]:
        """Combine what a scoped caller asked for with what they cannot see.

        Two rules, and the second is the one worth knowing.

        A firm they may not staff cannot be named at all -- refused by name
        rather than dropped, because a request that silently does less than it
        said is how somebody comes to believe a user was added.

        And **a scoped caller does not move the primary firm.** It is one flag
        across every firm a person belongs to, held by
        `UQ_user_firms_active_primary`, so setting it here would either collide
        with a primary in a firm this caller cannot see or quietly demote it.
        The existing primary is preserved; only where the person has none at
        all does the first membership take it, so a new hire still lands
        somewhere when they sign in.

        Raises:
            BusinessRuleError: If a firm outside the caller's reach is named.

        """
        named = {item.firm_id for item in assignments}
        beyond = named - allowed_firm_ids
        if beyond:
            raise BusinessRuleError("You can only assign firms you administer.")
        existing = list(
            self._session.scalars(
                select(UserFirm).where(
                    UserFirm.user_id == user_id,
                    UserFirm.is_deleted.is_(False),
                )
            )
        )
        untouched = [
            UserFirmAssignment(
                firm_id=row.firm_id,
                is_primary=row.is_primary,
                is_active=row.is_active,
            )
            for row in existing
            if row.firm_id not in allowed_firm_ids
        ]
        held_primary = next(
            (row.firm_id for row in existing if row.is_active and row.is_primary),
            None,
        )
        combined = untouched + [
            UserFirmAssignment(
                firm_id=item.firm_id,
                is_primary=item.firm_id == held_primary,
                is_active=item.is_active,
            )
            for item in assignments
        ]
        if held_primary is None or not any(
            item.is_primary and item.is_active for item in combined
        ):
            for index, item in enumerate(combined):
                if item.is_active:
                    combined[index] = UserFirmAssignment(
                        firm_id=item.firm_id, is_primary=True, is_active=True
                    )
                    break
        return combined

    def list_user_firms(
        self, user_id: UUID, visible_firm_ids: frozenset[UUID] | None = None
    ) -> list[UserFirm]:
        """Return the memberships of one user that this caller may see.

        `visible_firm_ids` is the caller's reach; None is every firm, which is
        what a platform caller has always had.

        It was unconditionally every membership, on a route gated only by
        `ROLE_VIEW` -- so any firm administrator who had a user id could read
        which firms that person belongs to. That is precisely the fact one
        firm must not learn about another, and it leaked for every user on the
        platform rather than only for shared ones.

        Args:
            user_id: The person whose memberships are wanted.
            visible_firm_ids: The firms the caller may see, or None for all.

        Returns:
            The memberships within reach, newest first is not meaningful here
            so the natural order is kept.

        """
        # A platform caller (reach None) may read a deleted user's firms: the
        # view dialog on a deleted row reads them, and a restore keeps them.
        self._get_user(user_id, include_deleted=visible_firm_ids is None)
        conditions = [UserFirm.user_id == user_id, UserFirm.is_deleted.is_(False)]
        if visible_firm_ids is not None:
            conditions.append(UserFirm.firm_id.in_(visible_firm_ids))
        return list(self._session.scalars(select(UserFirm).where(*conditions)))

    def describe_me(self, user_id: UUID) -> tuple[User, bool, UUID | None]:
        """Return the signed-in user, their designation and their primary firm.

        The self-service read behind `GET /me`. It answers for the caller
        only, so it needs no scope and no permission code: a person is always
        entitled to know who they are signed in as.
        """
        user = self._get_user(user_id)
        primary = self._session.scalar(
            select(UserFirm.firm_id)
            .join(Firm, Firm.id == UserFirm.firm_id)
            .where(
                UserFirm.user_id == user_id,
                UserFirm.is_primary.is_(True),
                UserFirm.is_active.is_(True),
                UserFirm.is_deleted.is_(False),
                Firm.is_active.is_(True),
                Firm.is_deleted.is_(False),
            )
        )
        return user, self._is_platform_admin(user.id), primary

    def list_my_roles(self, user_id: UUID) -> list[tuple[Role, Firm | None]]:
        """Return every role the signed-in user holds, with the firm it is in.

        The global tier comes back with no firm. Self-service, so no scope
        applies: a person is entitled to know what they may do, in every firm
        they belong to, which is more than a firm administrator's scoped read
        of them would show.
        """
        rows = self._session.execute(
            select(Role, Firm)
            .join(UserRole, UserRole.role_id == Role.id)
            .outerjoin(Firm, Firm.id == UserRole.firm_id)
            .where(
                UserRole.user_id == user_id,
                UserRole.is_deleted.is_(False),
                Role.is_deleted.is_(False),
                Role.is_active.is_(True),
            )
            .order_by(UserRole.firm_id.is_not(None), Role.code.asc())
        )
        return [(row[0], row[1]) for row in rows]

    def set_own_primary_firm(self, user_id: UUID, firm_id: UUID) -> None:
        """Make one of the caller's own firms the one they land in at sign-in.

        Self-service: `PUT /users/{id}/firms` sets the same flag, but it is an
        administrator's route, replaces the whole membership list, and a firm
        administrator of one firm may not move a primary they cannot see.
        Where a person lands is their own decision, so this touches the flag
        alone and only among firms they actively belong to.

        The old primary is cleared and **flushed** before the new one is set:
        `UQ_user_firms_active_primary` is a partial unique index checked per
        statement, so setting the new flag first would collide with the old.
        """
        user = self._get_user_for_update(user_id)
        memberships = list(
            self._session.scalars(
                select(UserFirm)
                .join(Firm, Firm.id == UserFirm.firm_id)
                .where(
                    UserFirm.user_id == user.id,
                    UserFirm.is_active.is_(True),
                    UserFirm.is_deleted.is_(False),
                    Firm.is_active.is_(True),
                    Firm.is_deleted.is_(False),
                )
                .with_for_update()
            )
        )
        chosen = next((row for row in memberships if row.firm_id == firm_id), None)
        if chosen is None:
            raise BusinessRuleError(
                "You can only make a firm you belong to your primary firm."
            )
        if chosen.is_primary:
            return
        for row in memberships:
            if row.is_primary:
                row.is_primary = False
                row.updated_by = user.id
        self._session.flush()
        chosen.is_primary = True
        chosen.updated_by = user.id
        record_audit(
            self._session,
            action="user.primary_firm_set",
            entity_type="user",
            entity_id=user.id,
            actor_id=user.id,
            firm_id=firm_id,
        )
        self._session.commit()

    def list_my_firms(
        self, user_id: UUID, *, every_firm: bool = False
    ) -> list[tuple[UserFirm | None, Firm]]:
        """Return the firms this user may work in.

        `every_firm` is for a platform administrator whose reach is
        `ALL_FIRMS`. Their designation already exempts them from the
        membership check in `app/common/scope.py`, so the server accepts an
        `X-Firm-ID` for any firm -- but this list is what the desktop's firm
        switcher offers, and it returned memberships only. The reach a
        designation confers therefore depended on somebody having remembered
        to insert `user_firms` rows: `superadmin` and `master.ops` were seeded
        into all four firms and worked, while the bootstrap
        `platform-admin@agency.local` had none and was offered an **empty**
        switcher, so every firm-owned screen its token unlocked opened onto a
        request it could not send.

        The membership still comes back where one exists, because it carries
        `is_primary`. A firm reached by the designation alone has no row and
        yields `None`, which is why the tuple's first element is optional.
        """
        self._get_user(user_id)
        if not every_firm:
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

        # Ranked explicitly rather than by `is_primary.desc()`: most firms
        # have no membership row here, so that column is NULL for them, and
        # PostgreSQL sorts NULLs first in DESC while SQLite sorts them last --
        # the ordering would differ between the tests and the deployment.
        primary_first = case((UserFirm.is_primary.is_(True), 0), else_=1)
        rows = self._session.execute(
            select(UserFirm, Firm)
            .select_from(Firm)
            .outerjoin(
                UserFirm,
                and_(
                    UserFirm.firm_id == Firm.id,
                    UserFirm.user_id == user_id,
                    UserFirm.is_active.is_(True),
                    UserFirm.is_deleted.is_(False),
                ),
            )
            .where(Firm.is_active.is_(True), Firm.is_deleted.is_(False))
            .order_by(primary_first, Firm.name.asc())
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
        admin_scope = self._platform_admin_scope(user.id)
        is_platform_admin = admin_scope is not None
        #: Whether the designation carries the two bypasses -- the permission
        #: short-circuit and the firm-membership exemption. A `PLATFORM`
        #: administrator keeps neither: they run the platform, and a firm's
        #: books are the firm's business.
        acts_in_every_firm = admin_scope is PlatformAdminScope.ALL_FIRMS
        # Deliberately **not** appended to `roles`. It used to be, as the
        # lowercase string `"platform_admin"` -- while genuine role codes are
        # uppercase -- so a designation and a role code shared one list.
        # `RoleCreate.code` requires `^[a-z0-9._-]+$`, so `platform_admin` was
        # a spellable code: a firm administrator holding `ROLE_CREATE` and
        # `ROLE_ASSIGN` could create that role, assign it to themselves, and
        # sign in as a platform administrator. It is its own claim now, and
        # nothing a user can name reaches it.
        if is_platform_admin:
            # A platform administrator holds no role rows, so the codes are
            # stuffed in rather than resolved. For a `PLATFORM` one that set
            # has to be narrowed here as well as at the two gates: the global
            # `permissions` claim is checked directly by `has_permission`, so
            # a stuffed operational code would pass every firm permission
            # check the moment they held a genuine membership -- tier 2 by the
            # back door, through a claim rather than a bypass.
            codes = select(Permission.code).where(
                Permission.is_deleted.is_(False),
                Permission.is_active.is_(True),
            )
            if not acts_in_every_firm:
                codes = codes.where(
                    Permission.code.in_(PLATFORM_OPERATOR_PERMISSION_CODES)
                )
            permissions = list(self._session.scalars(codes))
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
        # Computed for a `PLATFORM` administrator too. They have no exemption,
        # so if they hold a real membership they act there as whatever their
        # roles make them -- and the desktop needs the map to know it.
        if not acts_in_every_firm:
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
            "platform_admin": is_platform_admin,
            "platform_admin_scope": admin_scope.value if admin_scope else None,
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

    def _handle_refresh_reuse(self, token_hash: str, *, user_id: UUID) -> None:
        """Revoke every session when an already-rotated token is presented again.

        A refresh token is single use. Seeing one that was previously rotated
        means either the holder replayed a stale token or an attacker captured
        it, and the two are indistinguishable from here. Revoking the whole
        family is the safe reading: a legitimate user re-authenticates, while a
        stolen token loses the session it was rotated into.
        """
        replayed = self._session.scalar(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_not(None),
            )
        )
        if replayed is None:
            return
        self._revoke_user_tokens(user_id)
        record_audit(
            self._session,
            action="identity.refresh_token_reuse_detected",
            entity_type="user",
            entity_id=user_id,
            actor_id=user_id,
            after_data={"revoked_token_id": str(replayed.id)},
        )
        self._session.commit()

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

    #: The shortest term a **firm** caller's lookup will act on. `"a"` must
    #: not return the platform.
    LOOKUP_MINIMUM_TERM = 3

    #: How many a **firm** caller's lookup answers with. It answers "is this
    #: them?", not "who works here?" -- there is deliberately no paging for
    #: them, so the result is not a directory somebody can walk.
    LOOKUP_LIMIT = 10

    def lookup_users(
        self,
        term: str,
        firm_scope: UUID | None = None,
        *,
        hiring_firm_id: UUID | None = None,
        page: int = 1,
        page_size: int = LOOKUP_LIMIT,
    ) -> tuple[list[tuple[User, bool]], int]:
        """Find people by name or email, across firms, for hiring.

        `list_users` is scoped to the caller's own firm, deliberately -- and
        that leaves a firm administrator unable to hire somebody who already
        has an account, or even to learn that they exist. This is the opening
        for that one job, and it answers two callers differently, because the
        two are entitled to different things.

        **A firm caller gets a lookup, not a directory.** The people outside
        their firm are other firms' staff, so the limits are the design: a
        minimum term, a hard cap with no paging (`page` and `page_size` are
        ignored and anything past the first page is empty), and a result that
        says who somebody is and **never which firms they belong to** -- that
        last is the fact one firm must not learn about another. Their own
        members are returned and flagged rather than hidden, so a name that
        matches nothing is not mistaken for a person with no account.

        **A platform caller gets the directory**, which is theirs anyway: an
        empty term lists everybody with an account who is **not already in
        `hiring_firm_id`** (the firm selected in the switcher), paged, and a
        term filters that list. Members are excluded rather than flagged --
        the ask is "who can I add", and the firm's own people are in the grid
        beside the button. With no firm in context nothing is excluded.

        Platform administrators never appear for either caller, mirroring
        `list_users`. Enumeration by walking prefixes remains possible for a
        firm caller; that is accepted and written down rather than defended
        against, since `create_user` already answers 409 on a duplicate email
        and is a narrower oracle of the same kind.

        Args:
            term: What the administrator typed -- a name or an email, or
                nothing at all.
            firm_scope: The caller's firm, or None for a platform caller.
            hiring_firm_id: The firm being staffed, for a platform caller.
            page: Which page, for a platform caller.
            page_size: How many per page, for a platform caller.

        Returns:
            The people on this page, each with whether they are already a
            member of the caller's firm, and how many match in all.

        Raises:
            ValidationError: If a firm caller's term is too short to act on.

        """
        needle = term.strip()
        if firm_scope is not None and len(needle) < self.LOOKUP_MINIMUM_TERM:
            raise ValidationError(
                f"Type at least {self.LOOKUP_MINIMUM_TERM} characters to look "
                "somebody up."
            )
        not_a_platform_admin = ~User.id.in_(
            select(PlatformAdmin.user_id).where(PlatformAdmin.is_deleted.is_(False))
        )
        conditions: list[ColumnElement[bool]] = [
            User.is_deleted.is_(False),
            not_a_platform_admin,
        ]
        if needle:
            pattern = f"%{needle}%"
            conditions.append(
                or_(User.email.ilike(pattern), User.full_name.ilike(pattern))
            )

        if firm_scope is not None:
            if page > 1:
                return [], 0
            rows = list(
                self._session.scalars(
                    select(User)
                    .where(*conditions)
                    .order_by(User.full_name.asc(), User.email.asc())
                    .limit(self.LOOKUP_LIMIT)
                )
            )
            members = set(
                self._session.scalars(
                    select(UserFirm.user_id).where(
                        UserFirm.user_id.in_([row.id for row in rows]),
                        UserFirm.firm_id == firm_scope,
                        UserFirm.is_active.is_(True),
                        UserFirm.is_deleted.is_(False),
                    )
                )
            )
            return [(row, row.id in members) for row in rows], len(rows)

        if hiring_firm_id is not None:
            conditions.append(
                ~User.id.in_(
                    select(UserFirm.user_id).where(
                        UserFirm.firm_id == hiring_firm_id,
                        UserFirm.is_active.is_(True),
                        UserFirm.is_deleted.is_(False),
                    )
                )
            )
        total = int(
            self._session.scalar(
                select(func.count()).select_from(User).where(*conditions)
            )
            or 0
        )
        rows = list(
            self._session.scalars(
                select(User)
                .where(*conditions)
                .order_by(User.full_name.asc(), User.email.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return [(row, False) for row in rows], total

    def shared_user_ids(
        self, user_ids: list[UUID], firm_scope: UUID | None
    ) -> set[UUID]:
        """Return which of these people also work in a firm the caller cannot see.

        `_assert_exclusive_firm_user` refuses `update_user` and `delete_user`
        for exactly these, so a screen that does not know cannot disable the
        button -- it lets somebody fill in a form that was never going to
        save. One query for the page rather than one per row.

        Empty for a platform caller: they see every firm, so nothing is hidden
        and the guard does not apply to them.
        """
        if firm_scope is None or not user_ids:
            return set()
        return set(
            self._session.scalars(
                select(UserFirm.user_id).where(
                    UserFirm.user_id.in_(user_ids),
                    UserFirm.firm_id != firm_scope,
                    UserFirm.is_active.is_(True),
                    UserFirm.is_deleted.is_(False),
                )
            )
        )

    def _get_user(
        self,
        user_id: UUID,
        firm_scope: UUID | None = None,
        *,
        include_deleted: bool = False,
    ) -> User:
        """Resolve one user the caller may see, or 404.

        `include_deleted` is for a platform caller's **reads**: what a deleted
        person had -- their firms, their roles -- is part of deciding whether
        to bring them back, and the desktop's view dialog reads both as it
        opens. A firm caller never gets it, and no write passes it.
        """
        statement = select(User).where(User.id == user_id)
        if not include_deleted:
            statement = statement.where(User.is_deleted.is_(False))
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
                "This person also works in another firm, so their profile is "
                "managed by a platform administrator. You can still set their "
                "roles and job template in your own firm."
            )

    def _get_role(self, role_id: UUID, firm_scope: UUID | None = None) -> Role:
        statement = select(Role).where(Role.id == role_id, Role.is_deleted.is_(False))
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

    def _replace_global_user_roles(
        self, user_id: UUID, role_ids: list[UUID], actor_id: UUID
    ) -> None:
        """Replace the roles a user holds in **every** firm.

        Scoped rows are carried through untouched: a global grant and a firm's
        own grant are different decisions by different administrators, and
        neither may silently undo the other. This mirrors `set_user_firms`,
        which merges rather than replaces for the same reason.
        """
        existing_by_role = {
            item.role_id: item
            for item in self._session.scalars(
                select(UserRole).where(
                    UserRole.user_id == user_id,
                    UserRole.firm_id.is_(None),
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
                        firm_id=None,
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

    def set_user_firm_roles(
        self,
        user_id: UUID,
        firm_id: UUID,
        role_ids: list[UUID],
        actor_id: UUID,
        allowed_firm_ids: frozenset[UUID] | None = None,
    ) -> None:
        """Replace what one user does in one firm.

        The only way a firm-tier role is granted. A platform caller reaches
        every firm the user belongs to and names the one they mean; a firm
        caller is held to `allowed_firm_ids`, the firms where they themselves
        hold `USER_CREATE`.

        Deleting a role here removes it in this firm and nowhere else, which
        is what makes a firm administrator's edit an override without any
        precedence rule to reason about.
        """
        if allowed_firm_ids is not None and firm_id not in allowed_firm_ids:
            raise BusinessRuleError("You can only set roles in firms you administer.")
        user = self._get_user(user_id, firm_id if allowed_firm_ids else None)
        self._ensure_identifiers(Role, role_ids)
        membership = self._session.scalar(
            select(UserFirm).where(
                UserFirm.user_id == user.id,
                UserFirm.firm_id == firm_id,
                UserFirm.is_active.is_(True),
                UserFirm.is_deleted.is_(False),
            )
        )
        if membership is None:
            raise BusinessRuleError(
                "Add the user to this firm before giving them a role in it."
            )
        allowed_count = self._session.scalar(
            select(func.count())
            .select_from(Role)
            .where(
                Role.id.in_(role_ids),
                Role.is_deleted.is_(False),
                or_(Role.firm_id == firm_id, Role.code.in_(FIRM_ROLE_CODES)),
            )
        )
        if int(allowed_count or 0) != len(role_ids):
            raise BusinessRuleError("Platform or cross-firm roles cannot be assigned.")
        self._replace_scoped_user_roles(user.id, role_ids, actor_id, firm_id)
        self._revoke_user_tokens(user.id)
        record_audit(
            self._session,
            action="user.firm_roles_set",
            entity_type="user",
            entity_id=user.id,
            actor_id=actor_id,
            firm_id=firm_id,
        )
        self._session.commit()

    def list_user_global_role_ids(self, user_id: UUID) -> list[UUID]:
        """Return the roles a user holds in every firm.

        Read by a firm administrator too, and shown to them **read-only**:
        these apply in their firm and are not theirs to change, so hiding them
        would under-report what the person can actually do there -- which is
        what the old per-firm read did.
        """
        return list(
            self._session.scalars(
                select(UserRole.role_id).where(
                    UserRole.user_id == user_id,
                    UserRole.firm_id.is_(None),
                    UserRole.is_deleted.is_(False),
                )
            )
        )

    def list_user_firm_role_ids(
        self,
        user_id: UUID,
        firm_id: UUID,
        firm_scope: UUID | None = None,
        allowed_firm_ids: frozenset[UUID] | None = None,
    ) -> list[UUID]:
        """Return the roles one user holds in one firm.

        `allowed_firm_ids` is the caller's reach, the same set
        `set_user_firm_roles` is held to; None means every firm. The user is
        resolved first so somebody outside the caller's scope still answers
        404 rather than confirming they exist with a 403.
        """
        self._get_user(user_id, firm_scope, include_deleted=firm_scope is None)
        if allowed_firm_ids is not None and firm_id not in allowed_firm_ids:
            raise BusinessRuleError("You can only read roles in firms you administer.")
        return list(
            self._session.scalars(
                select(UserRole.role_id).where(
                    UserRole.user_id == user_id,
                    UserRole.firm_id == firm_id,
                    UserRole.is_deleted.is_(False),
                )
            )
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

    #: Names a role may not take. The platform designation is no longer
    #: carried in the `roles` claim, so spelling it is already harmless -- this
    #: is the second lock, because a role that merely *looks* like a
    #: designation is a trap for whoever reads a token next. The seeded codes
    #: are reserved for the same reason: a custom `firm_admin` beside the
    #: system `FIRM_ADMIN` is a support call waiting to happen.
    _RESERVED_ROLE_CODES = frozenset(
        {"platform_admin"} | {code.lower() for code in SYSTEM_ROLE_CODES}
    )

    def _assert_code_is_not_reserved(self, code: str) -> None:
        """Refuse a role code that impersonates a designation or a system role.

        Raises:
            BusinessRuleError: If the code is reserved.

        """
        if code.strip().lower() in self._RESERVED_ROLE_CODES:
            raise BusinessRuleError(
                f"'{code}' is reserved. Choose a different role code."
            )

    def _is_platform_admin(self, user_id: UUID) -> bool:
        return self._platform_admin_scope(user_id) is not None

    def _platform_admin_scope(self, user_id: UUID) -> PlatformAdminScope | None:
        """Return how far this user's platform designation reaches, or None.

        An unreadable stored value resolves to `PLATFORM`, the narrow one. A
        column holding something nobody recognises is a reason to grant less,
        never more.
        """
        stored = self._session.scalar(
            select(PlatformAdmin.scope).where(
                PlatformAdmin.user_id == user_id,
                PlatformAdmin.is_deleted.is_(False),
            )
        )
        if stored is None:
            return None
        try:
            return PlatformAdminScope(stored)
        except ValueError:
            return PlatformAdminScope.PLATFORM


def _hash_token(token: str) -> str:
    """Hash a bearer refresh token before persistence lookup."""
    return sha256(token.encode("utf-8")).hexdigest()


def _build_dummy_password_hash() -> str:
    """Return a hash used only to equalise login timing for unknown accounts.

    The plaintext is a generated UUID that is discarded, so nothing can ever
    verify against it.
    """
    return PasswordSecurity().hash_password(str(uuid4()))


#: Computed once at import so the equalising verify costs the same as a real one.
_DUMMY_PASSWORD_HASH = _build_dummy_password_hash()
