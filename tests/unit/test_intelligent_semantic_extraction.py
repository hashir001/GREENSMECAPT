"""Tests for grounded intelligent semantic extraction."""

from hashlib import sha256
from pathlib import Path

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
from greensmecapt.domain import (
    EvidenceValidationStatus,
    SourceDocument,
)

CATALOG_PATH = Path(
    "config/metric_catalog.development.json"
)


class FakeProvider:
    """Return controlled structured claims."""

    provider_name = "fake_provider"
    provider_version = "1.0"
    model_name = "fake_model"

    def __init__(
        self,
        claims: tuple[SemanticClaimPayload, ...],
    ) -> None:
        self._claims = claims

    def extract(self, request):
        assert request.document_id == "doc_llm_001"

        return SemanticProviderOutput(
            claims=self._claims
        )


def _document() -> SourceDocument:
    content = b"semantic provider test"

    return SourceDocument(
        document_id="doc_llm_001",
        sme_id="sme_001",
        file_name="environmental-report.pdf",
        mime_type="application/pdf",
        sha256=sha256(content).hexdigest(),
    )


def _extracted_document() -> ExtractedDocument:
    return ExtractedDocument(
        document_id="doc_llm_001",
        pages=(
            ExtractedPage(
                page_number=1,
                text=(
                    "Nearly three quarters of our electricity "
                    "was renewable. The measured renewable "
                    "energy contribution was 72 percent."
                ),
                text_source=TextSource.OCR,
            ),
        ),
    )


def _claim(
    **updates,
) -> SemanticClaimPayload:
    values = {
        "segment_id": "page_1_text",
        "indicator_id": (
            "renewable_energy_percentage"
        ),
        "raw_value": "72 percent",
        "raw_number": 72.0,
        "raw_unit": "percent",
        "source_quote": (
            "The measured renewable energy contribution "
            "was 72 percent."
        ),
    }
    values.update(updates)

    return SemanticClaimPayload(**values)


def _extract(*claims):
    service = IntelligentSemanticExtractionService(
        FakeProvider(tuple(claims))
    )

    return service.extract(
        document=_document(),
        extracted_document=_extracted_document(),
        catalog=load_metric_catalog(CATALOG_PATH),
    )


def test_convert_grounded_claim_to_evidence() -> None:
    """A fully grounded claim should become evidence."""

    report = _extract(_claim())

    assert len(report.evidence_items) == 1
    assert report.rejected_claims == ()

    evidence = report.evidence_items[0]

    assert evidence.normalized_value == 72.0
    assert evidence.unit == "percent"
    assert (
        evidence.validation_status
        is EvidenceValidationStatus.UNVALIDATED
    )
    assert (
        evidence.extraction_method
        == "language_model_structured_extraction"
    )


def test_reject_invented_source_quote() -> None:
    """A model must not cite text absent from the segment."""

    report = _extract(
        _claim(
            source_quote=(
                "Renewable energy contribution was 99 percent."
            )
        )
    )

    assert report.evidence_items == ()
    assert len(report.rejected_claims) == 1
    assert "does not occur" in (
        report.rejected_claims[0].reason
    )


def test_reject_unknown_segment() -> None:
    """A claim cannot invent its source location."""

    report = _extract(
        _claim(segment_id="page_99_text")
    )

    assert report.evidence_items == ()
    assert "unknown source segment" in (
        report.rejected_claims[0].reason
    )


def test_reject_unconfigured_indicator() -> None:
    """A model cannot invent an assessment indicator."""

    report = _extract(
        _claim(indicator_id="imaginary_metric")
    )

    assert report.evidence_items == ()
    assert "unconfigured indicator" in (
        report.rejected_claims[0].reason
    )


def test_reject_unit_absent_from_raw_value() -> None:
    """The model cannot attach a unit absent from its value."""

    report = _extract(
        _claim(raw_unit="%")
    )

    assert report.evidence_items == ()
    assert "does not occur in the raw value" in (
        report.rejected_claims[0].reason
    )


def test_reject_out_of_range_value() -> None:
    """Metric bounds should be enforced after extraction."""

    report = _extract(
        _claim(
            raw_value="72 percent",
            raw_number=172.0,
        )
    )

    assert report.evidence_items == ()
    assert "exceeds the metric maximum" in (
        report.rejected_claims[0].reason
    )