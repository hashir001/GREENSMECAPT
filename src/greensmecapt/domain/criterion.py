"""Domain model for an SME assessment criterion."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class CriterionDirection(StrEnum):
    """Describe whether a higher or lower criterion value is preferable."""

    BENEFIT = "benefit"
    COST = "cost"


class Criterion(BaseModel):
    """Define one criterion used to assess SMEs."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    criterion_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str | None = None
    direction: CriterionDirection