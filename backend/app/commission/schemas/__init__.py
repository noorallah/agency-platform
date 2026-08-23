"""Commission request and response schemas."""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CommissionSchema(BaseModel):
    """Apply strict input and ORM response behaviour."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class CommissionRuleStatusEnum(StrEnum):
    """Whether a rule is in force."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class CommissionRuleCreate(CommissionSchema):
    """Declare one commission rate.

    `salesman_id` omitted -- or sent as null -- is the firm-wide default, which
    is the rate anybody with no rule of their own earns.
    """

    salesman_id: UUID | None = None
    percentage: Decimal = Field(ge=0, le=100, max_digits=9, decimal_places=4)
    effective_from: date
    effective_to: date | None = None
    status: CommissionRuleStatusEnum = CommissionRuleStatusEnum.ACTIVE

    @model_validator(mode="after")
    def _window_runs_forwards(self) -> "CommissionRuleCreate":
        """Refuse a window that closes before it opens.

        Returns:
            The validated payload.

        Raises:
            ValueError: If the end of the window precedes its start.

        """
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to cannot be before effective_from.")
        return self


class CommissionRuleUpdate(CommissionSchema):
    """Change part of a commission rule.

    Every field is optional and the service dumps with ``exclude_unset``, so an
    omitted field means *leave it alone* while an explicit null still clears
    `effective_to` or moves a rule to the firm-wide scope. A write model that
    dumps in full turns an omission into an instruction, and that has shipped
    here often enough to be a rule rather than a preference.
    """

    salesman_id: UUID | None = None
    percentage: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=9, decimal_places=4
    )
    effective_from: date | None = None
    effective_to: date | None = None
    status: CommissionRuleStatusEnum | None = None


class CommissionRuleResponse(CommissionSchema):
    """Return one commission rule."""

    id: UUID
    salesman_id: UUID | None
    #: Empty for the firm-wide default, which belongs to nobody in particular.
    salesman_name: str
    percentage: Decimal
    effective_from: date
    effective_to: date | None
    status: CommissionRuleStatusEnum
    version: int


class SalesmanCommissionRecord(CommissionSchema):
    """What one salesman collected in the period, and what it earned them."""

    #: Null is the Unassigned bucket: money collected against invoices that
    #: carried no salesman. It belongs to nobody and is reported rather than
    #: dropped, because a total that silently omits it cannot be reconciled
    #: against the cash book.
    salesman_id: UUID | None
    salesman_name: str
    collected_amount: Decimal
    commission_amount: Decimal
    invoice_count: int


class CommissionSalesman(CommissionSchema):
    """One person a commission rate can be agreed with.

    A rate is per salesman, so the screen that sets one needs the firm's
    people **by name**. `users` lives only in the platform schema behind
    `USER_VIEW` -- a platform-admin permission a commission manager does not
    hold -- and the territory module's twin of this list is gated on
    `TERRITORY_ASSIGN_SALESMEN`, which they do not hold either. Without a list
    of its own the screen could only offer people who already had a rule, so a
    brand-new rate could never be agreed from it.
    """

    user_id: UUID
    full_name: str
    email: str


class CommissionReport(CommissionSchema):
    """Commission earned across a period, by salesman."""

    from_date: date
    to_date: date
    total_collected_amount: Decimal
    total_commission_amount: Decimal
    rows: list[SalesmanCommissionRecord]


__all__ = [
    "CommissionReport",
    "CommissionRuleCreate",
    "CommissionRuleResponse",
    "CommissionRuleStatusEnum",
    "CommissionRuleUpdate",
    "CommissionSalesman",
    "CommissionSchema",
    "SalesmanCommissionRecord",
]
