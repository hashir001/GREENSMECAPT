"""Domain model for a small or medium-sized enterprise."""

from pydantic import BaseModel, ConfigDict, Field


class SME(BaseModel):
    """Represent one SME assessed by GREENSMECAPT."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    sme_id: str = Field(min_length=1)
    legal_name: str = Field(min_length=1)
    sector: str = Field(min_length=1)
    jurisdiction: str = Field(min_length=1)