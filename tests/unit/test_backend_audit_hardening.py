"""Regression tests for audited backend integrity boundaries."""

from hashlib import sha256
from pathlib import Path

import pytest

from greensmecapt.assessment.observations import (
    ObservationStatus,
    build_observations,
)
from greensmecapt.assessment.profiles import (
    AssessmentContext,
    build_profile,
    load_policy,
)
from greensmecapt.document_intelligence.models import (
    ExtractedDocument,
    ExtractedPage,
    TextSource,
)
from greensmecapt.document_intelligence.semantics import (
    load_metric_catalog,
)
from greensmecapt.document_intelligence.semantics.intelligence import (
    IntelligentSemanticExtractionService,
    SemanticClaimPayload,
    SemanticProviderOutput,
)
from greensmecapt.document_intelligence.structure.paddle import (
    PaddleResourceProfile,
)
from greensmecapt.domain import (
    EvidenceItem,
    EvidenceValidationStatus,
    SourceDocument,
)
from greensmecapt.services.factory import (
    DocumentProcessingConfigurationError,
    production_reader_configuration_from_environment,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = (
    PROJECT_ROOT
    / "config"
    / "assessment_profiles.development.json"
)
CATALOG_PATH = (
    PROJECT_ROOT
    / "config"
    / "metric_catalog.development.json"
)


class _MismatchedNumberProvider:
    """Return a grounded quote with a false numeric payload."""

    provider_name = "fake_provider"
    provider_version = "1.0"
    model_name = "fake_model"

    def extract(
        self,
        request,
    ) -> SemanticProviderOutput:
        return SemanticProviderOutput(
            claims=(
                SemanticClaimPayload(
                    segment_id="page_1_text",
                    indicator_id=(
                        "renewable_energy_percentage"
                    ),
                    raw_value="72 percent",
                    raw_number=27.0,
                    raw_unit="percent",
                    source_quote=(
                        "Renewable energy share was "
                        "72 percent."
                    ),
                ),
            )
        )


def _profile():
    context = AssessmentContext(
        sme_id="sme_001",
        activity_description=(
            "A small manufacturer."
        ),
        facts={
            "manufactures_or_processes": True,
            "operates_facility": True,
        },
    )

    return build_profile(
        context,
        load_policy(POLICY_PATH),
    )


def _evidence(
    evidence_id: str,
    *,
    reporting_period: str,
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        sme_id="sme_001",
        document_id=(
            f"document_{evidence_id}"
        ),
        indicator_id=(
            "renewable_energy_percentage"
        ),
        criterion_id=(
            "purchased_energy_management"
        ),
        raw_value="72 percent",
        normalized_value=72.0,
        unit="percent",
        reporting_period=reporting_period,
        scope="company_operations",
        source_locator="page 1",
        extraction_method=(
            "semantic_rule_page_text"
        ),
        extractor_name="semantic_metric_rules",
        validation_status=(
            EvidenceValidationStatus.ACCEPTED
        ),
    )


def test_preserve_evidence_period_and_scope_in_observation() -> None:
    result = build_observations(
        _profile(),
        evidence_items=(
            _evidence(
                "evidence_001",
                reporting_period="FY2025",
            ),
        ),
    )
    observation = next(
        item
        for item in result.observations
        if (
            item.criterion_id
            == "purchased_energy_management"
        )
    )

    assert (
        observation.status
        is ObservationStatus.READY_NUMERIC
    )
    assert (
        observation.reporting_period
        == "FY2025"
    )
    assert (
        observation.scope
        == "company_operations"
    )


def test_do_not_merge_equal_values_from_different_periods() -> None:
    result = build_observations(
        _profile(),
        evidence_items=(
            _evidence(
                "evidence_001",
                reporting_period="FY2024",
            ),
            _evidence(
                "evidence_002",
                reporting_period="FY2025",
            ),
        ),
    )
    observation = next(
        item
        for item in result.observations
        if (
            item.criterion_id
            == "purchased_energy_management"
        )
    )

    assert (
        observation.status
        is ObservationStatus.NEEDS_SELECTION
    )
    assert (
        "periods or scopes"
        in observation.issues[0]
    )


def test_reject_provider_number_not_written_in_raw_value() -> None:
    content = b"semantic grounding test"
    document = SourceDocument(
        document_id="doc_001",
        sme_id="sme_001",
        file_name="report.pdf",
        mime_type="application/pdf",
        sha256=sha256(content).hexdigest(),
    )
    extracted = ExtractedDocument(
        document_id=document.document_id,
        pages=(
            ExtractedPage(
                page_number=1,
                text=(
                    "Renewable energy share was "
                    "72 percent."
                ),
                text_source=TextSource.OCR,
            ),
        ),
    )

    report = IntelligentSemanticExtractionService(
        _MismatchedNumberProvider()
    ).extract(
        document=document,
        extracted_document=extracted,
        catalog=load_metric_catalog(
            CATALOG_PATH
        ),
    )

    assert report.evidence_items == ()
    assert len(report.rejected_claims) == 1
    assert (
        "does not match"
        in report.rejected_claims[0].reason
    )


def test_default_ocr_profile_remains_safe_for_small_cpu() -> None:
    configuration = (
        production_reader_configuration_from_environment(
            {}
        )
    )

    assert (
        configuration.paddle.profile
        is PaddleResourceProfile.LOCAL_CPU
    )
    assert (
        configuration.paddle.cpu_threads
        == 2
    )
    assert (
        configuration.paddle.use_table_recognition
        is False
    )


def test_enable_full_scanned_table_profile_from_environment() -> None:
    configuration = (
        production_reader_configuration_from_environment(
            {
                "GREENSMECAPT_PADDLE_PROFILE": (
                    "full_structure"
                ),
                "GREENSMECAPT_PADDLE_DEVICE": "cpu",
                "GREENSMECAPT_PADDLE_CPU_THREADS": "4",
            }
        )
    )

    assert (
        configuration.paddle.profile
        is PaddleResourceProfile.FULL_STRUCTURE
    )
    assert (
        configuration.paddle.cpu_threads
        == 4
    )
    assert (
        configuration.paddle.use_table_recognition
        is True
    )
    assert (
        configuration.paddle.use_region_detection
        is True
    )


def test_reject_unknown_ocr_profile() -> None:
    with pytest.raises(
        DocumentProcessingConfigurationError,
        match="PADDLE_PROFILE",
    ):
        production_reader_configuration_from_environment(
            {
                "GREENSMECAPT_PADDLE_PROFILE": (
                    "enormous_magic_model"
                ),
            }
        )