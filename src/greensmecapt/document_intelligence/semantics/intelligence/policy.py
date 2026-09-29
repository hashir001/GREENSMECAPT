"""Versioned policy for grounded company and document understanding."""

from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class CompanyIntelligencePolicyError(ValueError):
    """Raised when the company-intelligence policy cannot be loaded."""


class PolicyModel(BaseModel):
    """Strict immutable policy model."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class DocumentTypeInstruction(PolicyModel):
    """Describe one controlled document class."""

    document_type_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    definition: str = Field(min_length=1)


class CompanyProfileFieldInstruction(PolicyModel):
    """Describe one source-grounded company fact."""

    field_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)


class SectorInstruction(PolicyModel):
    """Describe one controlled broad sector proposal."""

    sector_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    definition: str = Field(min_length=1)


class UnmappedMaterialCategory(PolicyModel):
    """Describe one review-only discovery category."""

    category_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    definition: str = Field(min_length=1)


class CompanyIntelligencePolicy(PolicyModel):
    """Govern open-world discovery around a closed assessment schema."""

    policy_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    status: str = Field(min_length=1)
    document_types: tuple[DocumentTypeInstruction, ...] = Field(min_length=1)
    company_profile_fields: tuple[CompanyProfileFieldInstruction, ...] = Field(
        min_length=1
    )
    sectors: tuple[SectorInstruction, ...] = Field(min_length=1)
    unmapped_material_categories: tuple[UnmappedMaterialCategory, ...] = Field(
        min_length=1
    )
    maximum_unmapped_claims_per_document: int = Field(default=10, ge=0, le=50)

    @model_validator(mode="after")
    def validate_unique_identifiers(self) -> Self:
        """Keep every controlled vocabulary unambiguous."""

        collections = {
            "document type": [item.document_type_id for item in self.document_types],
            "company field": [item.field_id for item in self.company_profile_fields],
            "sector": [item.sector_id for item in self.sectors],
            "unmapped category": [
                item.category_id for item in self.unmapped_material_categories
            ],
        }
        for label, identifiers in collections.items():
            if len(identifiers) != len(set(identifiers)):
                raise ValueError(f"{label.title()} identifiers must be unique.")
        return self


def load_company_intelligence_policy(
    path: str | Path,
) -> CompanyIntelligencePolicy:
    """Read and validate a versioned company-intelligence policy."""

    policy_path = Path(path)
    try:
        raw_content = policy_path.read_text(encoding="utf-8")
    except OSError as error:
        raise CompanyIntelligencePolicyError(
            f"Company-intelligence policy could not be read: {policy_path}"
        ) from error

    try:
        return CompanyIntelligencePolicy.model_validate_json(raw_content)
    except ValidationError as error:
        raise CompanyIntelligencePolicyError(
            f"Company-intelligence policy is invalid: {policy_path}"
        ) from error
