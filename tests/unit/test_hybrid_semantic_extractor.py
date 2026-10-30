"""Tests for hybrid deterministic and intelligent semantics."""

from hashlib import sha256
from pathlib import Path

import pytest

from greensmecapt.document_intelligence.models import (
    ExtractedDocument,
    ExtractedPage,
    TextSource,
)
from greensmecapt.document_intelligence.semantics import (
    SemanticMetricExtractor,
    load_metric_catalog,
)
from greensmecapt.document_intelligence.semantics.intelligence import (
    CandidateClassification,
    CandidateClassificationOutput,
    CandidateDisposition,
    IntelligentSemanticExtractionService,
    SemanticClaimPayload,
    SemanticProviderError,
    SemanticProviderOutput,
)
from greensmecapt.document_intelligence.understanding import (
    HybridSemanticConfiguration,
    HybridSemanticExtractionError,
    HybridSemanticExtractor,
    IntelligentProviderStatus,
)
from greensmecapt.domain import SourceDocument

CATALOG = load_metric_catalog(
    Path("config/metric_catalog.development.json")
)


class ClaimProvider:
    """Return a grounded claim missed by deterministic rules."""

    provider_name = "test_provider"
    provider_version = "1.0"
    model_name = "test_model"

    def extract(self, request):
        return SemanticProviderOutput(
            claims=(
                SemanticClaimPayload(
                    segment_id="page_1_text",
                    indicator_id=(
                        "renewable_energy_percentage"
                    ),
                    raw_value="72 percent",
                    raw_number=72,
                    raw_unit="percent",
                    source_quote=(
                        "Our audited clean-power proportion "
                        "stood at 72 percent."
                    ),
                ),
            )
        )


class FailingProvider:
    """Simulate an unavailable local or hosted model."""

    provider_name = "failing_provider"
    provider_version = "1.0"
    model_name = "unavailable_model"

    def extract(self, request):
        raise SemanticProviderError(
            "Provider is unavailable."
        )


class CandidateProvider:
    """Return one classified candidate also found by deterministic rules."""

    provider_name = "candidate_provider"
    provider_version = "1.0"
    model_name = "candidate_model"

    def extract(self, request):
        return SemanticProviderOutput()

    def classify_candidates(self, request):
        return CandidateClassificationOutput(
            classifications=tuple(
                CandidateClassification(
                    candidate_id=candidate.candidate_id,
                    disposition=CandidateDisposition.MAPPED,
                    indicator_id="renewable_energy_percentage",
                    claim_nature="actual",
                    reason="Explicit renewable-energy percentage.",
                )
                for candidate in request.candidates
            )
        )


def _document() -> SourceDocument:
    content = b"hybrid semantics"

    return SourceDocument(
        document_id="doc_hybrid_001",
        sme_id="sme_001",
        file_name="report.txt",
        mime_type="text/plain",
        sha256=sha256(content).hexdigest(),
    )


def _extracted(text: str) -> ExtractedDocument:
    return ExtractedDocument(
        document_id="doc_hybrid_001",
        pages=(
            ExtractedPage(
                page_number=1,
                text=text,
                text_source=TextSource.PLAIN_TEXT,
            ),
        ),
    )


def _hybrid(provider=None, *, required=False):
    intelligent_service = (
        IntelligentSemanticExtractionService(provider)
        if provider is not None
        else None
    )

    return HybridSemanticExtractor(
        deterministic_extractor=(
            SemanticMetricExtractor(CATALOG)
        ),
        catalog=CATALOG,
        intelligent_service=intelligent_service,
        configuration=HybridSemanticConfiguration(
            require_intelligent_success=required
        ),
    )


def test_run_without_intelligent_provider() -> None:
    """Rules should operate when no model is configured."""

    result = _hybrid().extract_with_diagnostics(
        document=_document(),
        extracted_document=_extracted(
            "Renewable energy share was 72 percent."
        ),
    )

    assert len(result.evidence_items) == 1
    assert (
        result.report.intelligent_provider_status
        is IntelligentProviderStatus.DISABLED
    )


def test_add_grounded_intelligent_evidence() -> None:
    """A model may recover language absent from the rule catalog."""

    result = _hybrid(
        ClaimProvider()
    ).extract_with_diagnostics(
        document=_document(),
        extracted_document=_extracted(
            "Our audited clean-power proportion "
            "stood at 72 percent."
        ),
    )

    assert len(result.evidence_items) == 1
    assert (
        result.evidence_items[0].normalized_value
        == 72.0
    )
    assert (
        result.report.intelligent_provider_status
        is IntelligentProviderStatus.SUCCEEDED
    )
    assert (
        len(result.report.intelligent_evidence_ids)
        == 1
    )


def test_prefer_intelligent_context_over_duplicate_rule_match() -> None:
    """The review queue should contain one copy of the same measurement."""

    result = _hybrid(
        CandidateProvider()
    ).extract_with_diagnostics(
        document=_document(),
        extracted_document=_extracted(
            "Renewable energy share was 72 percent."
        ),
    )

    assert len(result.evidence_items) == 1
    assert result.report.deterministic_evidence_ids == ()
    assert len(result.report.intelligent_evidence_ids) == 1
    assert result.evidence_items[0].claim_nature.value == "actual"


def test_fall_back_when_optional_provider_fails() -> None:
    """Provider failure should not erase deterministic evidence."""

    result = _hybrid(
        FailingProvider()
    ).extract_with_diagnostics(
        document=_document(),
        extracted_document=_extracted(
            "Renewable energy share was 72 percent."
        ),
    )

    assert len(result.evidence_items) == 1
    assert (
        result.report.intelligent_provider_status
        is IntelligentProviderStatus.FAILED
    )
    assert result.report.intelligent_provider_error == (
        "Provider is unavailable."
    )


def test_raise_when_required_provider_fails() -> None:
    """Strict deployments may require intelligent extraction."""

    with pytest.raises(
        HybridSemanticExtractionError,
        match="Provider is unavailable",
    ):
        _hybrid(
            FailingProvider(),
            required=True,
        ).extract_with_diagnostics(
            document=_document(),
            extracted_document=_extracted(
                "Renewable energy share was 72 percent."
            ),
        )
