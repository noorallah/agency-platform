"""Typed filter contracts for future repository query builders."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

type FilterValue = str | int | float | bool


class FilterOperator(StrEnum):
    """Supported generic filtering operations."""

    EQUALS = "eq"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    BETWEEN = "between"
    IN = "in"


class Filter(BaseModel):
    """Describe one validated filter without binding it to an ORM implementation."""

    model_config = ConfigDict(extra="forbid")

    field: str = Field(
        min_length=1, max_length=128, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$"
    )
    operator: FilterOperator
    value: FilterValue | list[FilterValue]

    @model_validator(mode="after")
    def validate_operator_value(self) -> "Filter":
        """Require collection values only for collection-oriented operators."""
        if self.operator is FilterOperator.IN and not isinstance(self.value, list):
            raise ValueError("The 'in' filter requires a list value.")
        if self.operator is FilterOperator.BETWEEN and not (
            isinstance(self.value, list) and len(self.value) == 2
        ):
            raise ValueError("The 'between' filter requires exactly two values.")
        if self.operator not in {
            FilterOperator.IN,
            FilterOperator.BETWEEN,
        } and isinstance(self.value, list):
            raise ValueError("This filter operator requires a scalar value.")
        return self
