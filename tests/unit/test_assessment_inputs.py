"""Tests for evidence-based assessment input resolution."""

import pytest
from pydantic import ValidationError

from greensmecapt.assessment.input_builder import (
    AssessmentInputBuilder,
    AssessmentInputError,
)
from greensmecapt.assessment.input_models import (
    AssessmentSpecification,
    IndicatorDefinition,
    InputStatus,
    NumericDirection,
)
from greensmecapt.domain import (
    SME,
    EvidenceItem,
    EvidenceValidationStatus,
    SourceDocument,
    StructuredInvestmentRecord,
)


def _definition(
    *,
    required: bool = True,
) -> IndicatorDefinition:
    return IndicatorDefinition(
        indicator_id="renewable_energy_percentage",
        criterion_id="renewable_energy",
        name="Renewable energy share",
        unit="percent",
        direction=NumericDirection.BENEFIT,
        minimum=0,
        maximum=100,
        required=required,
    )


def _specification(
    *,
    required: bool = True,
) -> AssessmentSpecification:
    return AssessmentSpecification(
        specification_id="test_green_assessment",
        version="0.1.0",
        indicators=(_definition(required=required),),
    )


def _evidence(
    value: str | int | float | bool = 72.0,
    *,
    evidence_id: str = "ev_001",
    sme_id: str = "sme_001",
    unit: str = "percent",
    criterion_id: str = "renewable_energy",
    status: EvidenceValidationStatus = EvidenceValidationStatus.ACCEPTED,
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        sme_id=sme_id,
        document_id=f"doc_{sme_id}",
        indicator_id="renewable_energy_percentage",
        criterion_id=criterion_id,
        raw_value=str(value),
        normalized_value=value,
        unit=unit,
        source_locator="page 1",
        extraction_method="test_fixture",
        extractor_name="test_fixture",
        validation_status=status,
    )


def _record(
    *evidence_items: EvidenceItem,
    sme_id: str = "sme_001",
) -> StructuredInvestmentRecord:
    return StructuredInvestmentRecord(
        sme=SME(
            sme_id=sme_id,
            legal_name=f"Example company {sme_id}",
            sector="Manufacturing",
            jurisdiction="United Arab Emirates",
        ),
        documents=(
            SourceDocument(
                document_id=f"doc_{sme_id}",
                sme_id=sme_id,
                file_name="statement.txt",
                mime_type="text/plain",
                sha256="a" * 64,
            ),
        ),
        evidence_items=evidence_items,
    )


def test_accepted_evidence_becomes_ready_input() -> None:
    result = AssessmentInputBuilder().build(
        _record(_evidence()),
        _specification(),
    )

    indicator = result.indicators[0]

    assert indicator.status is InputStatus.READY
    assert indicator.value == 72.0
    assert indicator.evidence_ids == ("ev_001",)
    assert result.required_inputs_ready
    assert result.all_inputs_ready
    assert result.specification_version == "0.1.0"


@pytest.mark.parametrize(
    "status",
    [
        EvidenceValidationStatus.UNVALIDATED,
        EvidenceValidationStatus.REJECTED,
    ],
)
def test_unaccepted_evidence_cannot_feed_assessment(
    status: EvidenceValidationStatus,
) -> None:
    result = AssessmentInputBuilder().build(
        _record(_evidence(status=status)),
        _specification(),
    )

    assert result.indicators[0].status is InputStatus.MISSING
    assert result.indicators[0].value is None
    assert not result.required_inputs_ready


def test_absent_indicator_is_missing_not_zero() -> None:
    result = AssessmentInputBuilder().build(
        _record(),
        _specification(),
    )

    assert result.indicators[0].status is InputStatus.MISSING
    assert result.indicators[0].value is None


def test_optional_missing_indicator_remains_visible() -> None:
    result = AssessmentInputBuilder().build(
        _record(),
        _specification(required=False),
    )

    assert result.required_inputs_ready
    assert not result.all_inputs_ready
    assert result.indicators[0].status is InputStatus.MISSING


@pytest.mark.parametrize(
    ("value", "unit", "criterion_id"),
    [
        (72.0, "kWh", "renewable_energy"),
        (101.0, "percent", "renewable_energy"),
        (-1.0, "percent", "renewable_energy"),
        (True, "percent", "renewable_energy"),
        ("seventy-two", "percent", "renewable_energy"),
        (72.0, "percent", "different_criterion"),
    ],
)
def test_invalid_evidence_blocks_resolution(
    value: str | int | float | bool,
    unit: str,
    criterion_id: str,
) -> None:
    result = AssessmentInputBuilder().build(
        _record(
            _evidence(
                value,
                unit=unit,
                criterion_id=criterion_id,
            )
        ),
        _specification(),
    )

    assert result.indicators[0].status is InputStatus.INVALID
    assert result.indicators[0].value is None
    assert result.indicators[0].issues
    assert not result.required_inputs_ready


def test_conflicting_values_require_resolution() -> None:
    result = AssessmentInputBuilder().build(
        _record(
            _evidence(72.0, evidence_id="ev_001"),
            _evidence(80.0, evidence_id="ev_002"),
        ),
        _specification(),
    )

    indicator = result.indicators[0]

    assert indicator.status is InputStatus.CONFLICT
    assert indicator.value is None
    assert indicator.evidence_ids == ("ev_001", "ev_002")


def test_agreeing_values_preserve_all_supporting_evidence() -> None:
    result = AssessmentInputBuilder().build(
        _record(
            _evidence(72.0, evidence_id="ev_002"),
            _evidence(72.0, evidence_id="ev_001"),
        ),
        _specification(),
    )

    indicator = result.indicators[0]

    assert indicator.status is InputStatus.READY
    assert indicator.value == 72.0
    assert indicator.evidence_ids == ("ev_001", "ev_002")


def test_valid_evidence_does_not_hide_invalid_accepted_evidence() -> None:
    result = AssessmentInputBuilder().build(
        _record(
            _evidence(72.0, evidence_id="ev_001"),
            _evidence(150.0, evidence_id="ev_002"),
        ),
        _specification(),
    )

    assert result.indicators[0].status is InputStatus.INVALID


def test_rejected_conflicting_value_does_not_block_accepted_value() -> None:
    result = AssessmentInputBuilder().build(
        _record(
            _evidence(72.0, evidence_id="ev_001"),
            _evidence(
                80.0,
                evidence_id="ev_002",
                status=EvidenceValidationStatus.REJECTED,
            ),
        ),
        _specification(),
    )

    assert result.indicators[0].status is InputStatus.READY
    assert result.indicators[0].value == 72.0
    assert result.indicators[0].evidence_ids == ("ev_001",)


def test_build_multiple_smes_under_one_specification() -> None:
    results = AssessmentInputBuilder().build_many(
        (
            _record(_evidence(72.0)),
            _record(
                _evidence(45.0, sme_id="sme_002"),
                sme_id="sme_002",
            ),
        ),
        _specification(),
    )

    assert [result.sme_id for result in results] == [
        "sme_001",
        "sme_002",
    ]
    assert [
        result.indicators[0].value for result in results
    ] == [72.0, 45.0]


def test_reject_duplicate_smes_in_batch() -> None:
    record = _record(_evidence())

    with pytest.raises(AssessmentInputError, match="unique"):
        AssessmentInputBuilder().build_many(
            (record, record),
            _specification(),
        )


def test_reject_empty_batch() -> None:
    with pytest.raises(AssessmentInputError, match="At least one"):
        AssessmentInputBuilder().build_many(
            (),
            _specification(),
        )


def test_reject_duplicate_indicator_definitions() -> None:
    with pytest.raises(ValidationError, match="unique"):
        AssessmentSpecification(
            specification_id="invalid_specification",
            version="0.1.0",
            indicators=(_definition(), _definition()),
        )


def test_reject_reversed_indicator_bounds() -> None:
    with pytest.raises(ValidationError, match="Minimum"):
        IndicatorDefinition(
            indicator_id="invalid_indicator",
            criterion_id="example",
            name="Invalid range",
            unit="percent",
            direction=NumericDirection.BENEFIT,
            minimum=100,
            maximum=0,
        )