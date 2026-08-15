"""Optimistic concurrency control for update endpoints.

``BaseEntity`` has carried a ``version`` column since the beginning, and nothing
ever read it: no ``version_id_col``, no ``If-Match``, no comparison anywhere.
Updates were last-writer-wins, and because a document update rebuilt its whole
line collection, two people editing the same document did not merge badly — one
of them simply lost every line they had entered.

The precondition is expressed with the standard HTTP header rather than a field
in the request body: an entity's version is transport metadata, not part of the
document a user is editing.

Sending no ``If-Match`` is still accepted, so existing clients keep working; a
client that wants protection opts in by sending the version it last read.

**The version has to be readable, or the precondition cannot be used.** Five
routers accepted ``If-Match`` from the day it was written while no response
carried the version anywhere -- not as a header, not as a body field -- so the
only value a client could honestly send was ``*``, which means "no
precondition". ``set_etag`` publishes it on every response that returns one
versioned record, which is what makes the header something a client can fill in
rather than a documented parameter nobody can use.
"""

from typing import Annotated

from fastapi import Depends, Header, Response

from app.core.database.entity import BaseEntity
from app.core.exceptions import ConflictError, ValidationError


def parse_if_match(
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> int | None:
    """Read the entity version a client expects to be updating.

    Args:
        if_match: The raw header. Quotes are tolerated so a caller may send a
            conventionally quoted ETag. ``*`` means "any version", which is the
            same as sending nothing.

    Returns:
        The expected version, or None when the caller did not specify one.

    Raises:
        ValidationError: If the header is neither ``*`` nor a version number.

    """
    if if_match is None:
        return None
    token = if_match.strip().strip('"').removeprefix("W/").strip('"')
    if token == "*":
        return None
    if not token.isdigit():
        raise ValidationError(
            "If-Match must be the entity version you last read, or *."
        )
    return int(token)


def assert_version(current: int, expected: int | None) -> None:
    """Refuse an update aimed at a version the record has moved past.

    Args:
        current: The version currently stored.
        expected: The version the caller believes it is updating.

    Raises:
        ConflictError: If the record changed since the caller read it.

    """
    if expected is not None and current != expected:
        raise ConflictError(
            "This record changed since you loaded it. Reload and try again."
        )


def set_etag(response: Response, entity: BaseEntity) -> None:
    """Publish the version a client must send back to update this record.

    The tag is the entity version in quotes, which is what ``parse_if_match``
    reads back, so a client can echo the header it was given without
    understanding what is inside it.

    Args:
        response: The response being returned to the caller.
        entity: The record whose version is being published.

    """
    response.headers["ETag"] = f'"{entity.version}"'


ExpectedVersion = Annotated[int | None, Depends(parse_if_match)]
