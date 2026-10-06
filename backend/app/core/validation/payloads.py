"""Read a request model out of text a handler was handed, as a 422 on refusal.

A JSON import arrives as a multipart form field, so FastAPI hands the handler
a string and the handler validates it itself. ``model_validate_json`` raises
pydantic's own ``ValidationError`` there, which is not the
``RequestValidationError`` FastAPI raises for a body it validated -- so it
reached the unhandled-exception handler, and eight import routes answered
**500 "An unexpected error occurred."** for any file their schema refused: two
lines numbered 1, a record with no customer, a quantity of "many", text that
is not JSON (D-PRC-76). Nothing was written, and the person importing was told
nothing about which record or why.

`parse_payload` is the one way a handler reads such text. A refusal is the
project's ``ValidationError`` -- 422, ``validation_error`` -- whose message
names the record and says what the single save would have said, with every
problem listed in ``details`` in the shape request validation uses.
"""

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from pydantic import BaseModel
from pydantic import ValidationError as SchemaRefusal

from app.core.exceptions.base import ApplicationError, ValidationError
from app.core.exceptions.handlers import plain_validator_message

#: The kinds of error whose message is a sentence one of our validators wrote.
_OUR_OWN = ("value_error", "assertion_error")
#: The list an import request keeps its records in.
_RECORDS = "records"


def _record_count(payload: str | bytes) -> int | None:
    """Return how many records the text holds, or None where it cannot say."""
    try:
        body = json.loads(payload)
    except ValueError:
        return None
    records = body.get(_RECORDS) if isinstance(body, dict) else None
    return len(records) if isinstance(records, list) else None


def _named(error: Mapping[str, Any], *, records: int | None) -> str:
    """Word one refusal, naming its record and, where it helps, its field.

    A sentence one of our own validators raised already says what is wrong
    and where ("Lines 1 and 2 of the request are both numbered 1."), so it
    stands alone after the record. One of pydantic's ("Field required") is
    nothing without its field: ``lines[2].quantity: Field required``.
    """
    path = list(error["loc"])
    message = plain_validator_message(error["msg"])
    prefix = ""
    if len(path) >= 2 and path[0] == _RECORDS and isinstance(path[1], int):
        of = "" if records is None else f" of {records}"
        prefix = f"Record {path[1] + 1}{of}: "
        path = path[2:]
    if error["type"] in _OUR_OWN or not path:
        return f"{prefix}{message}"
    field = ""
    for segment in path:
        if isinstance(segment, int):
            field += f"[{segment + 1}]"
        else:
            field += f".{segment}" if field else str(segment)
    return f"{prefix}{field}: {message}"


def parse_payload[ModelT: BaseModel](
    model: type[ModelT], payload: str | bytes
) -> ModelT:
    """Read ``model`` out of JSON text, refusing with a 422 that names the fault.

    Args:
        model: The request model the text must satisfy.
        payload: The text as it arrived, a form field or an uploaded file.

    Returns:
        The validated model.

    Raises:
        ValidationError: If the text is not JSON or the model refuses it. The
            message is the first problem -- "Record 2 of 2: Lines 1 and 2 of
            the request are both numbered 1. Number each line once." -- and
            ``details`` lists every one as ``field`` / ``message`` / ``code``.

    """
    try:
        return model.model_validate_json(payload)
    except SchemaRefusal as refusal:
        errors = refusal.errors(include_url=False, include_context=False)
        if any(error["type"] == "json_invalid" for error in errors):
            raise ValidationError(
                "The import is not valid JSON, so none of it was read. Check "
                "the file is the one exported for this import.",
                details=[
                    {
                        "field": "payload",
                        "message": plain_validator_message(errors[0]["msg"]),
                        "code": "json_invalid",
                    }
                ],
            ) from refusal
        records = _record_count(payload)
        messages = [_named(error, records=records) for error in errors]
        more = len(messages) - 1
        raise ValidationError(
            messages[0]
            + (
                ""
                if more <= 0
                else f" ({more} more problem{'s' if more > 1 else ''} in the "
                "details.)"
            ),
            details=[
                {
                    "field": ".".join(str(segment) for segment in error["loc"]),
                    "message": message,
                    "code": error["type"],
                }
                for error, message in zip(errors, messages, strict=True)
            ],
        ) from refusal


def stage_records[RecordT, RowT](
    records: Sequence[RecordT],
    stage: Callable[[RecordT], RowT],
    *,
    rollback: Callable[[], object],
) -> list[RowT]:
    """Stage every record of an import, naming the record a service refuses.

    A record the schema refuses is named by `parse_payload`. One the schema
    takes and the **service** then refuses -- a return line whose units are
    already back, an order for a customer on hold -- answered with the
    single save's sentence and nothing else, so in a file of two nobody
    could tell which record it was about (D-PRC-85). The refusal keeps its
    own class, status and details and reads "Record 2 of 2: ... Nothing was
    imported.", as a purchase return's import already did.

    Args:
        records: The file's records, in order.
        stage: Stages one record without committing.
        rollback: Undoes everything staged so far; called before any refusal
            or failure leaves, so the caller inherits no half-written file.

    Returns:
        What each record staged, in order, for the caller to commit once.

    Raises:
        ApplicationError: The first record's refusal, named by its number.

    """
    rows: list[RowT] = []
    for number, record in enumerate(records, start=1):
        try:
            rows.append(stage(record))
        except ApplicationError as error:
            rollback()
            error.message = (
                f"Record {number} of {len(records)}: {error.message} "
                "Nothing was imported."
            )
            error.args = (error.message,)
            raise
        except Exception:
            rollback()
            raise
    return rows


__all__ = ["parse_payload", "stage_records"]
