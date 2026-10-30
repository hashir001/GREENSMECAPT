"""Tests for grounded intelligent semantic extraction."""

from hashlib import sha256
from pathlib import Path

from greensmecapt.document_intelligence.models import (
    BoundingBox,
    ExtractedDocument,
    ExtractedPage,
    ExtractedTextBlock,
    TextSource,
)
from greensmecapt.document_intelligence.semantics import (
    load_metric_catalog,
)
from greensmecapt.document_intelligence.semantics.intelligence import (
    CandidateClassification,
    CandidateClassificationOutput,
    CandidateDisposition,
    CompanyProfileClaimPayload,
    DocumentProfileClaimPayload,
    IntelligentSemanticExtractionService,
    QualitativeClaimPayload,
    QualitativeInstruction,
    QualitativeValueType,
    ReadinessClaimPayload,
    ReadinessEvidenceState,
    ReadinessFactorInstruction,
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
        sector_activity_proposals: tuple[
            SectorActivityProposalPayload, ...
        ] = (),
        readiness_claims: tuple[ReadinessClaimPayload, ...] = (),
        unmapped_material_claims: tuple[
            UnmappedMaterialClaimPayload, ...
        ] = (),
    ) -> None:
        self._claims = claims
        self._qualitative_claims = qualitative_claims
        self._document_profile_claims = document_profile_claims
        self._company_profile_claims = company_profile_claims
        self._sector_activity_proposals = sector_activity_proposals
        self._readiness_claims = readiness_claims
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
            readiness_claims=self._readiness_claims,
            unmapped_material_claims=self._unmapped_material_claims,
        )


class CandidateProvider(FakeProvider):
    """Classify every enumerated candidate in a closed batch."""

    def __init__(self) -> None:
        super().__init__(())
        self.candidate_requests = []

    def classify_candidates(self, request):
        self.candidate_requests.append(request)
        classifications = []
        for candidate in request.candidates:
            if candidate.raw_number == 410000:
                classifications.append(
                    CandidateClassification(
                        candidate_id=candidate.candidate_id,
                        disposition=CandidateDisposition.MAPPED,
                        indicator_id="electricity_consumption_kwh",
                        reporting_period="2025",
                        scope="whole facility",
                        claim_nature="actual",
                        reason="2025 billed total electricity row.",
                    )
                )
            elif candidate.raw_number == 72:
                classifications.append(
                    CandidateClassification(
                        candidate_id=candidate.candidate_id,
                        disposition=CandidateDisposition.MAPPED,
                        indicator_id="renewable_energy_percentage",
                        reporting_period="2025",
                        scope="whole facility",
                        claim_nature="actual",
                        reason="2025 renewable-share row.",
                    )
                )
            else:
                classifications.append(
                    CandidateClassification(
                        candidate_id=candidate.candidate_id,
                        disposition=CandidateDisposition.IRRELEVANT,
                        reason="Comparator omitted by this controlled test.",
                    )
                )
        return CandidateClassificationOutput(
            classifications=tuple(classifications)
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


def test_reject_unit_absent_from_source_quote() -> None:
    """The model cannot attach a unit absent from its source quote."""

    report = _extract(
        _claim(raw_unit="%")
    )

    assert report.evidence_items == ()
    assert "does not occur in the source quote" in (
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


def test_ground_company_document_sector_and_unmapped_context() -> None:
    """Place grounded company and readiness context into human review."""

    quote = (
        "EcoPack LLC manufactures reusable packaging in Abu Dhabi and "
        "operates a production facility with ISO 14001 certification."
    )
    provider = FakeProvider(
        (),
        document_profile_claims=(
            DocumentProfileClaimPayload(
                segment_id="page_1_text",
                document_type_id="sustainability_or_esg_report",
                source_quote=quote,
            ),
        ),
        company_profile_claims=(
            CompanyProfileClaimPayload(
                segment_id="page_1_text",
                field_id="legal_name",
                raw_value="EcoPack LLC",
                source_quote=quote,
            ),
        ),
        sector_activity_proposals=(
            SectorActivityProposalPayload(
                segment_id="page_1_text",
                sector_id="manufacturing_and_processing",
                activity_fact_ids=("operates_facility",),
                source_quote=quote,
            ),
        ),
        readiness_claims=(
            ReadinessClaimPayload(
                segment_id="page_1_text",
                factor_id="regulation_compliance_standards_and_certifications",
                state=ReadinessEvidenceState.ENABLING,
                source_quote=quote,
                model_rationale="The source explicitly names ISO certification.",
            ),
        ),
        unmapped_material_claims=(
            UnmappedMaterialClaimPayload(
                segment_id="page_1_text",
                category_id="compliance_or_certification",
                suggested_label="ISO 14001 certification",
                source_quote=quote,
                model_rationale="Material certification evidence for review.",
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
        company_policy=load_company_intelligence_policy(COMPANY_POLICY_PATH),
        readiness_factors=(
            ReadinessFactorInstruction(
                factor_id="regulation_compliance_standards_and_certifications",
                title="Regulation, compliance and certification",
                definition="Ability to satisfy standards and certification requirements.",
            ),
        ),
    )
    extracted = ExtractedDocument(
        document_id="doc_llm_001",
        pages=(
            ExtractedPage(
                page_number=1,
                text=quote,
                text_source=TextSource.OCR,
            ),
        ),
    )

    report = service.extract(
        document=_document(),
        extracted_document=extracted,
        catalog=load_metric_catalog(CATALOG_PATH),
    )

    assert len(report.evidence_items) == 5
    assert all(
        item.validation_status is EvidenceValidationStatus.UNVALIDATED
        for item in report.evidence_items
    )
    assert any(
        item.indicator_id
        == "readiness_factor:regulation_compliance_standards_and_certifications"
        and item.normalized_value == "enabling_evidence"
        for item in report.evidence_items
    )
    assert report.rejected_claims == ()
    assert report.company_policy_version == "1.1.0"
    assert [claim.claim_type for claim in report.intelligence_claims] == [
        "document_profile",
        "company_profile",
        "sector_activity_proposal",
        "readiness_observation",
        "unmapped_material",
    ]
    assert report.intelligence_claims[2].related_ids == ("operates_facility",)


def test_reject_external_issuer_as_company_name() -> None:
    quote = (
        "ISSUED BY Emirates Industrial Utilities PJSC — "
        "Synthetic Research Provider"
    )
    provider = FakeProvider(
        (),
        company_profile_claims=(
            CompanyProfileClaimPayload(
                segment_id="page_1_text",
                field_id="legal_name",
                raw_value="Emirates Industrial Utilities PJSC",
                source_quote=quote,
            ),
        ),
    )
    service = IntelligentSemanticExtractionService(
        provider,
        company_policy=load_company_intelligence_policy(COMPANY_POLICY_PATH),
    )
    extracted = ExtractedDocument(
        document_id="doc_llm_001",
        pages=(
            ExtractedPage(
                page_number=1,
                text=quote,
                text_source=TextSource.OCR,
            ),
        ),
    )

    report = service.extract(
        document=_document(),
        extracted_document=extracted,
        catalog=load_metric_catalog(CATALOG_PATH),
    )

    assert report.evidence_items == ()
    assert "external document issuer" in report.rejected_claims[0].reason


def test_reconstruct_ocr_blocks_as_layout_rows() -> None:
    provider = FakeProvider(())
    service = IntelligentSemanticExtractionService(provider)
    extracted = ExtractedDocument(
        document_id="doc_llm_001",
        pages=(
            ExtractedPage(
                page_number=1,
                text=(
                    "Indicator 2024 comparator 2025 billed Unit\n"
                    "Certified renewable supply 45% 72% Share"
                ),
                text_source=TextSource.OCR,
                text_blocks=(
                    ExtractedTextBlock(
                        block_id="header_1",
                        text="Indicator",
                        bounding_box=BoundingBox(
                            x0=0.05, top=0.10, x1=0.25, bottom=0.14
                        ),
                        reading_order=0,
                    ),
                    ExtractedTextBlock(
                        block_id="header_2",
                        text="2025 billed",
                        bounding_box=BoundingBox(
                            x0=0.50, top=0.10, x1=0.68, bottom=0.14
                        ),
                        reading_order=1,
                    ),
                    ExtractedTextBlock(
                        block_id="metric",
                        text="Certified renewable supply",
                        bounding_box=BoundingBox(
                            x0=0.05, top=0.20, x1=0.38, bottom=0.24
                        ),
                        reading_order=2,
                    ),
                    ExtractedTextBlock(
                        block_id="value",
                        text="72%",
                        bounding_box=BoundingBox(
                            x0=0.50, top=0.20, x1=0.58, bottom=0.24
                        ),
                        reading_order=3,
                    ),
                ),
            ),
        ),
    )

    service.extract(
        document=_document(),
        extracted_document=extracted,
        catalog=load_metric_catalog(CATALOG_PATH),
    )

    assert len(provider.requests) == 1
    segment = provider.requests[0].segments[0]
    assert segment.segment_id == "page_1_layout"
    assert "Indicator | 2025 billed" in segment.text
    assert "Certified renewable supply | 72%" in segment.text


def test_keep_renewable_component_separate_from_total_electricity() -> None:
    quote = "The account includes 295,200 kWh of renewable supply."
    provider = FakeProvider(
        (
            SemanticClaimPayload(
                segment_id="page_1_text",
                indicator_id="electricity_consumption_kwh",
                raw_value="295,200 kWh",
                raw_number=295200,
                raw_unit="kWh",
                source_quote=quote,
            ),
            SemanticClaimPayload(
                segment_id="page_1_text",
                indicator_id="renewable_electricity_kwh",
                raw_value="295,200 kWh",
                raw_number=295200,
                raw_unit="kWh",
                source_quote=quote,
            ),
        )
    )
    service = IntelligentSemanticExtractionService(provider)
    extracted = ExtractedDocument(
        document_id="doc_llm_001",
        pages=(
            ExtractedPage(
                page_number=1,
                text=quote,
                text_source=TextSource.OCR,
            ),
        ),
    )

    report = service.extract(
        document=_document(),
        extracted_document=extracted,
        catalog=load_metric_catalog(CATALOG_PATH),
    )

    assert [item.indicator_id for item in report.evidence_items] == [
        "renewable_electricity_kwh"
    ]
    assert "cannot be classified as total" in report.rejected_claims[0].reason


def test_candidate_ledger_covers_utility_table_values() -> None:
    provider = CandidateProvider()
    service = IntelligentSemanticExtractionService(provider)
    extracted = ExtractedDocument(
        document_id="doc_llm_001",
        pages=(
            ExtractedPage(
                page_number=1,
                text=(
                    "Indicator 2024 comparator 2025 billed Unit boundary "
                    "Electricity consumption 460,000 410,000 kWh whole "
                    "facility Certified renewable supply 45% 72%"
                ),
                text_source=TextSource.OCR,
                text_blocks=(
                    ExtractedTextBlock(
                        block_id="header",
                        text=(
                            "Indicator | 2024 comparator | 2025 billed | "
                            "Unit / boundary"
                        ),
                        bounding_box=BoundingBox(
                            x0=0.05, top=0.10, x1=0.95, bottom=0.14
                        ),
                        reading_order=0,
                    ),
                    ExtractedTextBlock(
                        block_id="electricity_label",
                        text="Electricity consumption",
                        bounding_box=BoundingBox(
                            x0=0.05, top=0.20, x1=0.35, bottom=0.24
                        ),
                        reading_order=1,
                    ),
                    ExtractedTextBlock(
                        block_id="electricity_2024",
                        text="460,000",
                        bounding_box=BoundingBox(
                            x0=0.40, top=0.20, x1=0.50, bottom=0.24
                        ),
                        reading_order=2,
                    ),
                    ExtractedTextBlock(
                        block_id="electricity_2025",
                        text="410,000",
                        bounding_box=BoundingBox(
                            x0=0.55, top=0.20, x1=0.65, bottom=0.24
                        ),
                        reading_order=3,
                    ),
                    ExtractedTextBlock(
                        block_id="electricity_unit",
                        text="kWh — whole facility",
                        bounding_box=BoundingBox(
                            x0=0.70, top=0.20, x1=0.95, bottom=0.24
                        ),
                        reading_order=4,
                    ),
                    ExtractedTextBlock(
                        block_id="renewable_label",
                        text="Certified renewable supply",
                        bounding_box=BoundingBox(
                            x0=0.05, top=0.30, x1=0.35, bottom=0.34
                        ),
                        reading_order=5,
                    ),
                    ExtractedTextBlock(
                        block_id="renewable_2024",
                        text="45%",
                        bounding_box=BoundingBox(
                            x0=0.40, top=0.30, x1=0.50, bottom=0.34
                        ),
                        reading_order=6,
                    ),
                    ExtractedTextBlock(
                        block_id="renewable_2025",
                        text="72%",
                        bounding_box=BoundingBox(
                            x0=0.55, top=0.30, x1=0.65, bottom=0.34
                        ),
                        reading_order=7,
                    ),
                    ExtractedTextBlock(
                        block_id="renewable_unit",
                        text="Share of billed electricity — whole facility",
                        bounding_box=BoundingBox(
                            x0=0.70, top=0.30, x1=0.95, bottom=0.34
                        ),
                        reading_order=8,
                    ),
                ),
            ),
        ),
    )

    report = service.extract(
        document=_document(),
        extracted_document=extracted,
        catalog=load_metric_catalog(CATALOG_PATH),
    )

    values = {
        (item.indicator_id, item.normalized_value)
        for item in report.evidence_items
    }
    assert ("electricity_consumption_kwh", 410000) in values, report.rejected_claims
    assert ("renewable_energy_percentage", 72) in values
    assert report.numeric_candidate_count == 4
    assert report.classified_candidate_count == 4
    assert report.unresolved_candidate_count == 0


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


def test_provider_connection_check_uses_real_schema_contract() -> None:
    provider = FakeProvider(())
    service = IntelligentSemanticExtractionService(provider)

    result = service.check_connection()

    assert result.provider_name == "fake_provider"
    assert result.model_name == "fake_model"
    assert provider.requests[0].document_id == "provider_connection_check"
