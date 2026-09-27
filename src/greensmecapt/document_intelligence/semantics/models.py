"""Versioned semantic definitions for document metrics."""

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SemanticModel(BaseModel):
    """Base configuration for deterministic semantic extraction."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )


class UnitRule(SemanticModel):
    """Normalize equivalent written units into one canonical unit."""

    canonical_unit: str = Field(min_length=1)
    aliases: tuple[str, ...] = Field(min_length=1)
    multiplier: float = Field(default=1.0, gt=0)

    @model_validator(mode="after")
    def validate_unique_aliases(self) -> Self:
        """Prevent duplicate spellings inside one unit rule."""

        normalized = [
            _normalize_phrase(alias)
            for alias in self.aliases
        ]

        if len(normalized) != len(set(normalized)):
            raise ValueError(
                "Unit aliases must be unique after normalization."
            )

        return self


class MetricAssessmentUse(StrEnum):
    """Describe whether a metric is ready for comparative assessment."""

    DIRECT_RATIO = "direct_ratio"
    REQUIRES_COMPARISON_CONTEXT = "requires_comparison_context"
    EVIDENCE_ONLY = "evidence_only"


class MetricDefinition(SemanticModel):
    """Describe one assessment metric and its language variants."""

    indicator_id: str = Field(min_length=1)
    criterion_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    aliases: tuple[str, ...] = Field(min_length=1)
    units: tuple[UnitRule, ...] = Field(min_length=1)
    assessment_use: MetricAssessmentUse = MetricAssessmentUse.EVIDENCE_ONLY
    comparison_requirements: tuple[str, ...] = ()

    minimum: float | None = None
    maximum: float | None = None

    @model_validator(mode="after")
    def validate_definition(self) -> Self:
        """Reject ambiguous aliases and contradictory ranges."""

        normalized_aliases = [
            _normalize_phrase(alias)
            for alias in self.aliases
        ]

        if len(normalized_aliases) != len(
            set(normalized_aliases)
        ):
            raise ValueError(
                "Metric aliases must be unique after normalization."
            )

        unit_aliases = [
            _normalize_phrase(alias)
            for unit in self.units
            for alias in unit.aliases
        ]

        if len(unit_aliases) != len(set(unit_aliases)):
            raise ValueError(
                "Unit aliases must identify exactly one conversion."
            )

        canonical_units = {
            unit.canonical_unit
            for unit in self.units
        }

        if len(canonical_units) != 1:
            raise ValueError(
                "Every unit rule for one metric must normalize "
                "to the same canonical unit."
            )

        if len(self.comparison_requirements) != len(
            set(self.comparison_requirements)
        ):
            raise ValueError(
                "Metric comparison requirements must be unique."
            )

        if (
            self.assessment_use
            is MetricAssessmentUse.REQUIRES_COMPARISON_CONTEXT
            and not self.comparison_requirements
        ):
            raise ValueError(
                "Context-dependent metrics must declare comparison "
                "requirements."
            )

        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            raise ValueError(
                "Metric minimum must not exceed maximum."
            )

        return self

    @property
    def requires_comparison_context(self) -> bool:
        """Return whether the raw value is insufficient for comparison."""

        return (
            self.assessment_use
            is MetricAssessmentUse.REQUIRES_COMPARISON_CONTEXT
        )

    @property
    def canonical_unit(self) -> str:
        """Return the metric's normalized output unit."""

        return self.units[0].canonical_unit


class MetricCatalog(SemanticModel):
    """Versioned semantic vocabulary used during extraction."""

    catalog_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    metrics: tuple[MetricDefinition, ...] = Field(
        min_length=1
    )

    @model_validator(mode="after")
    def validate_catalog(self) -> Self:
        """Require unique indicators and unambiguous phrases."""

        indicator_ids = [
            metric.indicator_id
            for metric in self.metrics
        ]

        if len(indicator_ids) != len(set(indicator_ids)):
            raise ValueError(
                "Metric indicator IDs must be unique."
            )

        aliases: dict[str, str] = {}

        for metric in self.metrics:
            for alias in metric.aliases:
                normalized_alias = _normalize_phrase(alias)
                existing = aliases.get(normalized_alias)

                if (
                    existing is not None
                    and existing != metric.indicator_id
                ):
                    raise ValueError(
                        f"Alias {alias!r} is assigned to "
                        "multiple metrics."
                    )

                aliases[normalized_alias] = (
                    metric.indicator_id
                )

        return self


def _normalize_phrase(value: str) -> str:
    """Normalize configuration phrases for comparison."""

    return " ".join(value.casefold().split())
