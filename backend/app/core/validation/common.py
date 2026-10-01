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
#: A Tax Deduction Account Number: four letters, five digits, one letter.
_TAN_PATTERN = re.compile(r"^[A-Z]{4}[0-9]{5}[A-Z]$")
_PAN_PATTERN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")


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


def normalize_tan(value: str | None) -> str | None:
    """Return a TAN in capitals, None for a blank, or refuse a malformed one.

    For a pydantic ``field_validator``: the ``ValueError`` becomes a 422
    naming the field. The format is the Income Tax Department's -- four
    letters, five digits, one letter (``DELA12345B``) -- so a digit typed for
    a letter is caught while typing rather than on the quarterly return.

    Raises:
        ValueError: If a non-blank value is not in that format.

    """
    if value is None:
        return None
    normalized = value.strip().upper()
    if not normalized:
        return None
    if not _TAN_PATTERN.fullmatch(normalized):
        raise ValueError(
            "A TAN is four letters, five digits and a letter, e.g. DELA12345B."
        )
    return normalized


def normalize_pan(value: str | None) -> str | None:
    """Return a PAN in capitals, None for a blank, or refuse a malformed one.

    The Income Tax Department's format: five letters, four digits, one letter
    (``ABCDE1234F``). A TDS return names every deductee by PAN, so a wrong one
    is caught here rather than when the return bounces.

    Raises:
        ValueError: If a non-blank value is not in that format.

    """
    if value is None:
        return None
    normalized = value.strip().upper()
    if not normalized:
        return None
    if not _PAN_PATTERN.fullmatch(normalized):
        raise ValueError(
            "A PAN is five letters, four digits and a letter, e.g. ABCDE1234F."
        )
    return normalized


_GSTIN_PATTERN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


def normalize_gstin(value: str | None) -> str | None:
    """Return a GSTIN in capitals, None for a blank, refusing a wrong shape.

    Two digits of state, the holder's ten-character PAN, an entity number,
    ``Z`` and a check character. The check character itself is not verified
    here: the shape is what a typing slip breaks, and the portal is the
    authority on whether the number is real. A transporter's enrolment
    number (TRANSIN) has the same shape.
    """
    if value is None:
        return None
    normalized = "".join(value.split()).upper()
    if not normalized:
        return None
    if not _GSTIN_PATTERN.fullmatch(normalized):
        raise ValueError(
            "A GSTIN is 15 characters: two digits of state, the ten-character "
            "PAN, a digit or letter, Z and a check character, e.g. "
            "29ABCDE1234F1Z5."
        )
    return normalized


def _identifier(value: str | None) -> str | None:
    """Return an identifier in capitals without spaces, or None for a blank."""
    if value is None:
        return None
    normalized = value.strip().upper()
    return normalized or None


def pan_in_gstin(gstin: str | None) -> str | None:
    """Return the PAN a GSTIN is built on, or None when it carries none.

    A GSTIN is two digits of state, the holder's ten-character PAN, then three
    more characters, so characters 3 to 12 are the PAN. Some registrations
    are not built on a PAN (a UIN, a non-resident's), so a slice that is not
    in the PAN format says nothing about the PAN and is not compared.
    """
    normalized = _identifier(gstin)
    if normalized is None or len(normalized) != 15:
        return None
    candidate = normalized[2:12]
    return candidate if _PAN_PATTERN.fullmatch(candidate) else None


def settle_pan(
    *,
    pan: str | None,
    gstin: str | None,
    stored_pan: str | None = None,
    stored_gstin: str | None = None,
    creating: bool,
    pan_field: str,
    gstin_field: str,
) -> str | None:
    """Check a party's PAN against its GSTIN; return the PAN to store.

    Backlog 53 item 2, for every record that carries both (customer, vendor,
    the firm itself). ``pan`` and ``gstin`` are what the record will hold
    after the write; ``stored_*`` what it holds now.

    * A PAN is checked for its format only when it is being **set** -- on a
      create, or when the write moves it. A PAN typed before the check
      existed must not block somebody correcting a phone number; it is
      refused the next time somebody edits the PAN itself.
    * When either moves and the GSTIN is built on a PAN, a blank PAN is
      **filled** from it, and a PAN that disagrees is refused naming both.

    Raises:
        ValidationError: Naming the field (``details["field"]``) when the PAN
            is malformed or does not match the GSTIN.

    """
    pan = _identifier(pan)
    gstin = _identifier(gstin)
    pan_moved = creating or pan != _identifier(stored_pan)
    gstin_moved = creating or gstin != _identifier(stored_gstin)
    if pan and pan_moved and not _PAN_PATTERN.fullmatch(pan):
        raise ValidationError(
            f"PAN {pan} is not a PAN: a PAN is five letters, four digits and a "
            "letter, e.g. ABCDE1234F.",
            details={"field": pan_field},
        )
    if not (pan_moved or gstin_moved):
        return pan
    in_gstin = pan_in_gstin(gstin)
    if in_gstin is None:
        return pan
    if pan is None:
        return in_gstin
    if pan != in_gstin:
        raise ValidationError(
            f"PAN {pan} does not match GSTIN {gstin}: characters 3 to 12 of a "
            f"GSTIN are the holder's PAN, here {in_gstin}. Correct whichever "
            "of the two is wrong.",
            details={"field": pan_field, "fields": [pan_field, gstin_field]},
        )
    return pan


def check_tan_if_set(
    tan: str | None, *, stored_tan: str | None = None, creating: bool, field: str
) -> str | None:
    """Return a TAN in capitals, refusing a malformed one only when it is set.

    The rule ``settle_pan`` follows for a PAN, for a record whose TAN was
    stored before any check existed (a vendor's): checked on a create or
    when the write moves it, and left alone otherwise.

    Raises:
        ValidationError: Naming ``field`` when a TAN being set is malformed.

    """
    normalized = _identifier(tan)
    if normalized is None or (not creating and normalized == _identifier(stored_tan)):
        return normalized
    if not _TAN_PATTERN.fullmatch(normalized):
        raise ValidationError(
            f"TAN {normalized} is not a TAN: a TAN is four letters, five digits "
            "and a letter, e.g. DELA12345B.",
            details={"field": field},
        )
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
