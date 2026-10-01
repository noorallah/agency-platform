"""Request and answer shapes for acting on many documents at once (backlog 56 A).

`docs/BULK_APPROVAL_MIGRATION_AND_YEAR_DATA.md` section 2 is the design.
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: The most rows one request may name. Each row is its own transaction, so a
#: larger batch is only a longer wait with nothing to show for it.
MAX_BULK_ROWS = 100


class BulkActionSchema(BaseModel):
    """Base for the bulk shapes: unknown fields are refused."""

    model_config = ConfigDict(extra="forbid")


class BulkRow(BulkActionSchema):
    """One ticked document, and the version the list showed it at.

    The version guards against acting on a document somebody changed after
    the list was read; left out, the row is acted on as it stands, as a
    single action without an `If-Match` is.
    """

    id: UUID
    version: int | None = None


class BulkApproveRequest(BulkActionSchema):
    """The ticked documents to approve."""

    items: list[BulkRow] = Field(min_length=1, max_length=MAX_BULK_ROWS)


class BulkCancelRequest(BulkActionSchema):
    """The ticked documents to cancel, and why -- a reason is required."""

    items: list[BulkRow] = Field(min_length=1, max_length=MAX_BULK_ROWS)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def _reason_is_said(cls, value: str) -> str:
        """Refuse a reason of blanks: it records nothing."""
        if not value.strip():
            raise ValueError("A reason is required.")
        return value.strip()


class BulkRowResult(BulkActionSchema):
    """What happened to one row: done, or refused and why."""

    id: UUID
    number: str | None = None
    outcome: Literal["DONE", "REFUSED"]
    message: str | None = None


class BulkActionResult(BulkActionSchema):
    """Every row's outcome, in the order asked, with the two counts."""

    done: int
    refused: int
    results: list[BulkRowResult]
