"""Stateless UUID helpers."""

from uuid import UUID, uuid4


def new_uuid() -> UUID:
    """Generate a new random UUID."""
    return uuid4()


def parse_uuid(value: str) -> UUID:
    """Parse a UUID string into a UUID object."""
    return UUID(value)
