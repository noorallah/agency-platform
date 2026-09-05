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


class PlatformAdminScope(StrEnum):
    """How far a platform administrator's designation reaches.

    The platform has always had exactly one kind of administrator, who passes
    every permission check by short-circuit and every firm-membership check by
    exemption. That conflates two jobs a real deployment separates: **running
    the platform** -- creating firms, creating their people, provisioning
    storage, setting a firm up until it works -- and **acting inside a firm's
    books**, which is the firm's own business.

    A `PLATFORM` administrator does the first and is refused the second: they
    keep the platform surface and lose both bypasses, so a firm-owned route
    treats them as any other user and refuses them unless they hold a real
    membership. `ALL_FIRMS` is the designation as it has always behaved.

    Deliberately not a boolean. A third reach is easy to imagine -- one firm
    group, a support engineer with a time-boxed grant -- and a boolean named
    for one of two cases has to be renamed to admit a third.
    """

    PLATFORM = "PLATFORM"
    ALL_FIRMS = "ALL_FIRMS"
