"""Cross-cutting enumerations shared by future modules."""

from enum import StrEnum


class TokenType(StrEnum):
    """Identify the intended lifetime and use of a JWT."""

    ACCESS = "access"
    REFRESH = "refresh"


class UserStatus(StrEnum):
    """Describe a user's lifecycle status without encoding business policy."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    LOCKED = "locked"
