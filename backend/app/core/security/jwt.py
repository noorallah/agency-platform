"""JWT generation and validation utilities independent of HTTP endpoints."""

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from pydantic import BaseModel, ConfigDict, Field

from app.core.config.settings import JwtSettings
from app.core.enums import TokenType
from app.core.exceptions import AuthenticationError
from app.core.utils.dates import utc_now


class TokenClaims(BaseModel):
    """Represent the validated standard claims used by platform tokens."""

    model_config = ConfigDict(extra="allow", frozen=True)

    subject: str = Field(alias="sub")
    token_type: TokenType = Field(alias="type")
    issued_at: int = Field(alias="iat")
    expires_at: int = Field(alias="exp")


class JwtService:
    """Issue and validate access and refresh JWTs."""

    def __init__(self, settings: JwtSettings) -> None:
        """Store the signing settings needed for token operations."""
        self._settings = settings

    def generate_access_token(
        self, subject: UUID | str, *, claims: dict[str, Any] | None = None
    ) -> str:
        """Create a signed, short-lived access token."""
        return self._generate(
            subject,
            TokenType.ACCESS,
            timedelta(minutes=self._settings.access_token_minutes),
            claims,
        )

    def generate_refresh_token(
        self, subject: UUID | str, *, claims: dict[str, Any] | None = None
    ) -> str:
        """Create a signed, long-lived refresh token."""
        return self._generate(
            subject,
            TokenType.REFRESH,
            timedelta(days=self._settings.refresh_token_days),
            claims,
        )

    def validate_token(
        self, token: str, *, expected_type: TokenType | None = None
    ) -> TokenClaims:
        """Validate a token's signature, lifetime, and optional intended type."""
        try:
            payload = jwt.decode(
                token,
                self._settings.secret_key.get_secret_value(),
                algorithms=[self._settings.algorithm],
                options={"require": ["sub", "type", "iat", "exp"]},
            )
            token_claims = TokenClaims.model_validate(payload)
        except (ExpiredSignatureError, InvalidTokenError, ValueError) as error:
            raise AuthenticationError(
                "The authentication token is invalid or expired."
            ) from error

        if expected_type is not None and token_claims.token_type is not expected_type:
            raise AuthenticationError("The authentication token has an invalid type.")
        return token_claims

    def extract_claims(self, token: str) -> dict[str, Any]:
        """Return all validated token claims for framework integrations."""
        return self.validate_token(token).model_dump(by_alias=True)

    def _generate(
        self,
        subject: UUID | str,
        token_type: TokenType,
        lifetime: timedelta,
        additional_claims: dict[str, Any] | None,
    ) -> str:
        """Create a signed token with reserved claims protected from overrides."""
        now = utc_now()
        payload = dict(additional_claims or {})
        payload.update(
            {
                "sub": str(subject),
                "type": token_type.value,
                "iat": now,
                "exp": now + lifetime,
            }
        )
        if token_type is TokenType.REFRESH:
            payload["jti"] = str(uuid4())
        return jwt.encode(
            payload,
            self._settings.secret_key.get_secret_value(),
            algorithm=self._settings.algorithm,
        )
