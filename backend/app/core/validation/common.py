"""Stateless validation helpers shared by future API schemas and services."""

import re
from collections.abc import Iterable
from datetime import date

from pydantic import BaseModel

from app.core.exceptions import BusinessRuleError, ValidationError

_EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}"
    r"[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)
_PHONE_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")


def refuse_explicit_nulls(model: BaseModel, *, nullable: Iterable[str] = ()) -> None:
    """Refuse an explicit ``null`` for a field whose column cannot hold one.

    For a partial update, where every field is optional so that *absent* can
    mean "leave it alone". An explicit null on a NOT NULL column then reached
    the database and came back as a 409 "conflicts with existing data" -- a
    conflict with nothing (D-CFG-21). Called from a ``model_validator``, the
    ``ValueError`` becomes a 422 naming the field.

    Args:
        model: The validated payload.
        nullable: The fields for which null is a real value -- "clear it".

    Raises:
        ValueError: Naming each field sent as null that may not be.

    """
    allowed = frozenset(nullable)
    refused = sorted(
        name
        for name in model.model_fields_set
        if name not in allowed and getattr(model, name) is None
    )
    if refused:
        raise ValueError(
            f"{', '.join(refused)} cannot be null. Omit a field to leave it "
            "unchanged."
        )


def validate_email(value: str) -> str:
    """Normalize and validate an email address without storing identity data."""
    normalized = value.strip().casefold()
    if not _EMAIL_PATTERN.fullmatch(normalized):
        raise ValidationError("A valid email address is required.")
    return normalized


def validate_phone(value: str) -> str:
    """Validate a phone number in international E.164 format."""
    normalized = re.sub(r"[\s().-]", "", value)
    if not _PHONE_PATTERN.fullmatch(normalized):
        raise ValidationError("A valid E.164 phone number is required.")
    return normalized


def validate_password_policy(
    value: str,
    *,
    minimum_length: int = 12,
    require_uppercase: bool = True,
    require_lowercase: bool = True,
    require_digit: bool = True,
    require_symbol: bool = True,
) -> None:
    """Validate a policy without hashing, storing, or authenticating passwords."""
    violations: list[str] = []
    if len(value) < minimum_length:
        violations.append(f"must contain at least {minimum_length} characters")
    if require_uppercase and not any(character.isupper() for character in value):
        violations.append("must contain an uppercase letter")
    if require_lowercase and not any(character.islower() for character in value):
        violations.append("must contain a lowercase letter")
    if require_digit and not any(character.isdigit() for character in value):
        violations.append("must contain a digit")
    if require_symbol and value.isalnum():
        violations.append("must contain a symbol")
    if violations:
        raise ValidationError(
            "Password does not meet the configured policy.", details=violations
        )


def validate_date_range(start_date: date, end_date: date) -> None:
    """Ensure an inclusive date range has a non-decreasing boundary."""
    if start_date > end_date:
        raise ValidationError("The start date must not be after the end date.")


def ensure_business_rule(condition: bool, message: str) -> None:
    """Raise a standard business-rule error when a required condition is false."""
    if not condition:
        raise BusinessRuleError(message)
