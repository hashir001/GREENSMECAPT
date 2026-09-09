"""Resolve accepted document evidence into numeric assessment inputs."""

from collections.abc import Sequence
from math import isfinite

from greensmecapt.assessment.input_models import (
    AssessmentSpecification,
    IndicatorDefinition,
    InputStatus,
    ResolvedIndicator,
    SMEAssessmentInput,
)
from greensmecapt.domain import (
    EvidenceItem,
    EvidenceValidationStatus,
    StructuredInvestmentRecord,
)


class AssessmentInputError(ValueError):
    """Raised when assessment input assembly cannot proceed consistently."""


class AssessmentInputBuilder:
    """Build traceable numeric inputs without silently repairing evidence."""

    def build(
        self,
        record: StructuredInvestmentRecord,
        specification: AssessmentSpecification,
    ) -> SMEAssessmentInput:
        """Resolve each specified indicator for one SME."""

        evidence_by_indicator: dict[str, list[EvidenceItem]] = {}

        for evidence in record.evidence_items:
            evidence_by_indicator.setdefault(
                evidence.indicator_id, []
            ).append(evidence)

        resolved = tuple(
            self._resolve(
                definition,
                evidence_by_indicator.get(definition.indicator_id, []),
            )
            for definition in specification.indicators
        )

        return SMEAssessmentInput(
            sme_id=record.sme.sme_id,
            specification_id=specification.specification_id,
            specification_version=specification.version,
            indicators=resolved,
        )

    def build_many(
        self,
        records: Sequence[StructuredInvestmentRecord],
        specification: AssessmentSpecification,
    ) -> tuple[SMEAssessmentInput, ...]:
        """Resolve multiple SMEs against the same ordered definitions."""

        if not records:
            raise AssessmentInputError(
                "At least one SME record must be supplied."
            )

        sme_ids = [record.sme.sme_id for record in records]

        if len(sme_ids) != len(set(sme_ids)):
            raise AssessmentInputError(
                "SME IDs must be unique within an assessment batch."
            )

        return tuple(
            self.build(record, specification) for record in records
        )

    def _resolve(
        self,
        definition: IndicatorDefinition,
        candidates: Sequence[EvidenceItem],
    ) -> ResolvedIndicator:
        accepted = sorted(
            (
                evidence
                for evidence in candidates
                if evidence.validation_status
                is EvidenceValidationStatus.ACCEPTED
            ),
            key=lambda evidence: evidence.evidence_id,
        )

        if not accepted:
            return ResolvedIndicator(
                definition=definition,
                status=InputStatus.MISSING,
                issues=("No accepted evidence is available.",),
            )

        evidence_ids = tuple(
            evidence.evidence_id for evidence in accepted
        )
        issues: list[str] = []
        values: list[float] = []

        for evidence in accepted:
            prefix = f"{evidence.evidence_id}:"

            if (
                evidence.criterion_id is not None
                and evidence.criterion_id != definition.criterion_id
            ):
                issues.append(
                    f"{prefix} criterion does not match the definition."
                )

            if evidence.unit != definition.unit:
                issues.append(
                    f"{prefix} expected unit {definition.unit!r}, "
                    f"received {evidence.unit!r}."
                )

            value = evidence.normalized_value

            # bool is a subclass of int in Python, so reject it explicitly.
            if isinstance(value, bool) or not isinstance(
                value, (int, float)
            ):
                issues.append(
                    f"{prefix} normalized value must be numeric."
                )
                continue

            try:
                numeric_value = float(value)
            except (OverflowError, ValueError):
                issues.append(
                    f"{prefix} value cannot be represented as a finite number."
                )
                continue

            if not isfinite(numeric_value):
                issues.append(f"{prefix} value must be finite.")
                continue

            if (
                definition.minimum is not None
                and numeric_value < definition.minimum
            ):
                issues.append(
                    f"{prefix} value is below {definition.minimum}."
                )

            if (
                definition.maximum is not None
                and numeric_value > definition.maximum
            ):
                issues.append(
                    f"{prefix} value exceeds {definition.maximum}."
                )

            values.append(numeric_value)

        if issues:
            return ResolvedIndicator(
                definition=definition,
                status=InputStatus.INVALID,
                evidence_ids=evidence_ids,
                issues=tuple(issues),
            )

        if len(set(values)) != 1:
            return ResolvedIndicator(
                definition=definition,
                status=InputStatus.CONFLICT,
                evidence_ids=evidence_ids,
                issues=(
                    "Accepted evidence contains different values; "
                    "an explicit resolution is required.",
                ),
            )

        return ResolvedIndicator(
            definition=definition,
            status=InputStatus.READY,
            value=values[0],
            evidence_ids=evidence_ids,
        )