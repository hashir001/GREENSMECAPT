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
    CompanyProfileClaimPayload,
    DocumentProfileClaimPayload,
    IntelligentSemanticExtractionService,
    QualitativeClaimPayload,
    QualitativeInstruction,
    QualitativeValueType,
    SectorActivityProposalPayload,
    SemanticClaimPayload,
    SemanticProviderOutput,
    UnmappedMaterialClaimPayload,
    load_company_intelligence_policy,
)
from greensmecapt.document_intelligence.semantics.intelligence.service import (
    _raw_unit_occurs_in_value,
)
from greensmecapt.domain import (
    EvidenceValidationStatus,
    SourceDocument,
)

CATALOG_PATH = Path(
    "config/metric_catalog.development.json"
)
COMPANY_POLICY_PATH = Path(
    "config/company_intelligence.development.json"
)


class FakeProvider:
    """Return controlled structured claims."""

    provider_name = "fake_provider"
    provider_version = "1.0"
    model_name = "fake_model"

    def __init__(
        self,
        claims: tuple[SemanticClaimPayload, ...],
        qualitative_claims: tuple[QualitativeClaimPayload, ...] = (),
        document_profile_claims: tuple[DocumentProfileClaimPayload, ...] = (),
        company_profile_claims: tuple[CompanyProfileClaimPayload, ...] = (),
        sector_activity_proposals: tuple[SectorActivityProposalPayload, ...] = (),
        unmapped_material_claims: tuple[UnmappedMaterialClaimPayload, ...] = (),
    ) -> None:
        self._claims = claims
        self._qualitative_claims = qualitative_claims
        self._document_profile_claims = document_profile_claims
        self._company_profile_claims = company_profile_claims
        self._sector_activity_proposals = sector_activity_proposals
        self._unmapped_material_claims = unmapped_material_claims
        self.requests = []

    def extract(self, request):
        assert request.document_id in {
            "doc_llm_001",
            "provider_connection_check",
        }
        self.requests.append(request)

        return SemanticProviderOutput(
            claims=self._claims,
            qualitative_claims=self._qualitative_claims,
            document_profile_claims=self._document_profile_claims,
            company_profile_claims=self._company_profile_claims,
            sector_activity_proposals=self._sector_activity_proposals,
            unmapped_material_claims=self._unmapped_material_claims,
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


def test_ground_currency_scale_words_around_number() -> None:
    assert _raw_unit_occurs_in_value(
        raw_value="AED 3.20 million",
        raw_unit="AED million",
    )
    assert not _raw_unit_occurs_in_value(
        raw_value="AED 3.20 million",
        raw_unit="AED billion",
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


def test_extract_grounded_activity_fact_for_review() -> None:
    """An explicit activity fact should remain unvalidated evidence."""

    provider = FakeProvider(
        (),
        (
            QualitativeClaimPayload(
                segment_id="page_1_text",
                claim_id="activity_fact:operates_facility",
                source_quote=(
                    "The measured renewable energy contribution was "
                    "72 percent."
                ),
                boolean_value=True,
            ),
        ),
    )
    service = IntelligentSemanticExtractionService(
        provider,
        qualitative_instructions=(
            QualitativeInstruction(
                claim_id="activity_fact:operates_facility",
                name="operates facility",
                question="Does the company operate a facility?",
                value_type=QualitativeValueType.BOOLEAN,
            ),
        ),
    )

    report = service.extract(
        document=_document(),
        extracted_document=_extracted_document(),
        catalog=load_metric_catalog(CATALOG_PATH),
    )

    assert report.rejected_claims == ()
    assert len(report.evidence_items) == 1
    evidence = report.evidence_items[0]
    assert evidence.indicator_id == "activity_fact:operates_facility"
    assert evidence.normalized_value is True
    assert evidence.criterion_id is None
    assert evidence.validation_status is EvidenceValidationStatus.UNVALIDATED


def test_reject_qualitative_quote_absent_from_source() -> None:
    provider = FakeProvider(
        (),
        (
            QualitativeClaimPayload(
                segment_id="page_1_text",
                claim_id="criterion_context:green_contribution",
                source_quote="We prevent ten tonnes of waste every month.",
            ),
        ),
    )
    service = IntelligentSemanticExtractionService(
        provider,
        qualitative_instructions=(
            QualitativeInstruction(
                claim_id="criterion_context:green_contribution",
                name="Green contribution",
                question="What environmental benefit is provided?",
                value_type=QualitativeValueType.SOURCE_TEXT,
                criterion_id="green_contribution",
            ),
        ),
    )

    report = service.extract(
        document=_document(),
        extracted_document=_extracted_document(),
        catalog=load_metric_catalog(CATALOG_PATH),
    )

    assert report.evidence_items == ()
    assert "does not occur" in report.rejected_claims[0].reason


def test_partition_long_documents_into_bounded_requests() -> None:
    provider = FakeProvider(())
    service = IntelligentSemanticExtractionService(
        provider,
        maximum_segments_per_request=1,
    )
    extracted = ExtractedDocument(
        document_id="doc_llm_001",
        pages=(
            ExtractedPage(
                page_number=1,
                text="Renewable energy share was 72 percent.",
                text_source=TextSource.OCR,
            ),
            ExtractedPage(
                page_number=2,
                text="The company operates a workshop.",
                text_source=TextSource.OCR,
            ),
        ),
    )

    report = service.extract(
        document=_document(),
        extracted_document=extracted,
        catalog=load_metric_catalog(CATALOG_PATH),
    )

    assert report.request_count == 2
    assert len(provider.requests) == 2
    assert all(len(request.segments) == 1 for request in provider.requests)


def test_ground_company_document_sector_and_unmapped_context() -> None:
    text = (
        "AsterLoop Industries LLC publishes its 2025 Sustainability Report. "
        "The company manufactures packaging in Abu Dhabi and holds ISO 14001 "
        "certification. Its pilot also reports a biodiversity score of 17 "
        "points."
    )
    extracted = ExtractedDocument(
        document_id="doc_llm_001",
        pages=(
            ExtractedPage(
                page_number=1,
                text=text,
                text_source=TextSource.OCR,
            ),
        ),
    )
    provider = FakeProvider(
        (),
        document_profile_claims=(
            DocumentProfileClaimPayload(
                segment_id="page_1_text",
                document_type_id="sustainability_or_esg_report",
                source_quote=(
                    "AsterLoop Industries LLC publishes its 2025 "
                    "Sustainability Report."
                ),
                issuer_name="AsterLoop Industries LLC",
                reporting_period="2025",
            ),
        ),
        company_profile_claims=(
            CompanyProfileClaimPayload(
                segment_id="page_1_text",
                field_id="legal_name",
                raw_value="AsterLoop Industries LLC",
                source_quote=(
                    "AsterLoop Industries LLC publishes its 2025 "
                    "Sustainability Report."
                ),
            ),
        ),
        sector_activity_proposals=(
            SectorActivityProposalPayload(
                segment_id="page_1_text",
                sector_id="manufacturing_and_processing",
                activity_fact_ids=("manufactures_or_processes",),
                source_quote="The company manufactures packaging in Abu Dhabi",
            ),
        ),
        unmapped_material_claims=(
            UnmappedMaterialClaimPayload(
                segment_id="page_1_text",
                category_id="environmental_metric",
                suggested_label="Biodiversity score",
                source_quote="biodiversity score of 17 points",
                model_rationale=(
                    "This is a numeric environmental measure outside the "
                    "approved catalogue."
                ),
            ),
        ),
    )
    service = IntelligentSemanticExtractionService(
        provider,
        company_policy=load_company_intelligence_policy(COMPANY_POLICY_PATH),
        qualitative_instructions=(
            QualitativeInstruction(
                claim_id="activity_fact:manufactures_or_processes",
                name="manufactures or processes",
                question="Does the company manufacture physical products?",
                value_type=QualitativeValueType.BOOLEAN,
            ),
        ),
    )

    report = service.extract(
        document=_document(),
        extracted_document=extracted,
        catalog=load_metric_catalog(CATALOG_PATH),
    )

    assert report.rejected_claims == ()
    assert report.company_policy_version == "1.0.0"
    assert {claim.claim_type for claim in report.intelligence_claims} == {
        "document_profile",
        "company_profile",
        "sector_activity_proposal",
        "unmapped_material",
    }
    sector = next(
        claim
        for claim in report.intelligence_claims
        if claim.claim_type == "sector_activity_proposal"
    )
    assert sector.related_ids == ("manufactures_or_processes",)


def test_provider_connection_check_uses_real_schema_contract() -> None:
    provider = FakeProvider(())
    service = IntelligentSemanticExtractionService(provider)

    result = service.check_connection()

    assert result.provider_name == "fake_provider"
    assert result.model_name == "fake_model"
    assert provider.requests[0].document_id == "provider_connection_check"
