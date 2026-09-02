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


class CommissionBasisEnum(StrEnum):
    """What a rule is a percentage of."""

    COLLECTED = "COLLECTED"
    INVOICED = "INVOICED"


class CommissionSlabModeEnum(StrEnum):
    """How a ladder of rates reads."""

    MARGINAL = "MARGINAL"
    WHOLE_AMOUNT = "WHOLE_AMOUNT"


class CommissionSlabWrite(CommissionSchema):
    """One rung of a ladder.

    `to_amount` null is the open-ended top rung. The service checks that the
    rungs start at zero, meet exactly and only run out at the top, because a
    gap is an amount the rule cannot answer for and an overlap is two answers.
    """

    from_amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    to_amount: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=2
    )
    percentage: Decimal = Field(ge=0, le=100, max_digits=9, decimal_places=4)

    @model_validator(mode="after")
    def _band_runs_forwards(self) -> "CommissionSlabWrite":
        """Refuse a band that ends at or before it starts.

        Returns:
            The validated rung.

        Raises:
            ValueError: If the ceiling does not sit above the floor.

        """
        if self.to_amount is not None and self.to_amount <= self.from_amount:
            raise ValueError("to_amount must be above from_amount.")
        return self


class CommissionSlabResponse(CommissionSchema):
    """Return one rung."""

    sequence: int
    from_amount: Decimal
    to_amount: Decimal | None
    percentage: Decimal


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
    basis: CommissionBasisEnum = CommissionBasisEnum.COLLECTED
    slab_mode: CommissionSlabModeEnum = CommissionSlabModeEnum.MARGINAL
    max_commission_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )
    #: A ladder. Empty means the flat `percentage` above is the arrangement,
    #: which is every rule written before slabs existed.
    slabs: list[CommissionSlabWrite] = Field(default_factory=list)

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
    basis: CommissionBasisEnum | None = None
    slab_mode: CommissionSlabModeEnum | None = None
    max_commission_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )
    #: Omitted leaves the ladder alone; an empty list is an instruction to
    #: remove it and go back to the flat rate. The service reads
    #: `model_fields_set` to tell the two apart, because a write model that
    #: dumps in full turns an omission into an instruction.
    slabs: list[CommissionSlabWrite] | None = None


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
    basis: CommissionBasisEnum
    slab_mode: CommissionSlabModeEnum
    max_commission_amount: Decimal | None
    slabs: list[CommissionSlabResponse]
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
    #: Approved invoice value raised in the period and tagged to this person.
    #: Reported whatever the arrangement, because a firm paying on collections
    #: still wants to see what was billed against them -- and because a row on
    #: an INVOICED rule would otherwise show an earning with nothing behind it.
    invoiced_amount: Decimal
    #: COLLECTED, INVOICED, or MIXED where a rate change moved the arrangement
    #: mid-period. Empty for the Unassigned bucket, which no rule governs.
    basis: str
    commission_amount: Decimal
    invoice_count: int


class CommissionReport(CommissionSchema):
    """Commission earned across a period, by salesman."""

    from_date: date
    to_date: date
    total_collected_amount: Decimal
    total_invoiced_amount: Decimal
    total_commission_amount: Decimal
    rows: list[SalesmanCommissionRecord]


__all__ = [
    "CommissionBasisEnum",
    "CommissionReport",
    "CommissionRuleCreate",
    "CommissionRuleResponse",
    "CommissionRuleStatusEnum",
    "CommissionRuleUpdate",
    "CommissionSchema",
    "CommissionSlabModeEnum",
    "CommissionSlabResponse",
    "CommissionSlabWrite",
    "SalesmanCommissionRecord",
]
