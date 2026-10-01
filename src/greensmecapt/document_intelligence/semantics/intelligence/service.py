"""Ground intelligent semantic claims in document evidence."""

import logging
import re
from hashlib import sha256
from math import isclose

from greensmecapt.document_intelligence.models import (
    ExtractedDocument,
    ExtractedPage,
)
from greensmecapt.document_intelligence.semantics.context import (
    normalize_reporting_period,
    normalize_scope,
)
from greensmecapt.document_intelligence.semantics.intelligence.models import (
    CompanyProfileClaimPayload,
    DocumentProfileClaimPayload,
    GroundedIntelligenceClaim,
    IntelligentExtractionReport,
    MetricInstruction,
    QualitativeClaimPayload,
    QualitativeInstruction,
    QualitativeValueType,
    RejectedSemanticClaim,
    SectorActivityProposalPayload,
    SemanticClaimPayload,
    SemanticExtractionRequest,
    SemanticProviderConnection,
    SemanticSourceSegment,
    UnmappedMaterialClaimPayload,
)
from greensmecapt.document_intelligence.semantics.intelligence.policy import (
    CompanyIntelligencePolicy,
)
from greensmecapt.document_intelligence.semantics.intelligence.provider import (
    SemanticExtractionProvider,
)
from greensmecapt.document_intelligence.semantics.models import (
    MetricCatalog,
    MetricDefinition,
    UnitRule,
)
from greensmecapt.domain import EvidenceItem, SourceDocument

_LOGGER = logging.getLogger("uvicorn.error")

_WRITTEN_NUMBER_PATTERN = re.compile(
    r"(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?(?![\w.])"
)


class IntelligentSemanticExtractionService:
    """Convert only grounded provider claims into evidence."""

    def __init__(
        self,
        provider: SemanticExtractionProvider,
        *,
        qualitative_instructions: tuple[QualitativeInstruction, ...] = (),
        company_policy: CompanyIntelligencePolicy | None = None,
        maximum_segments_per_request: int = 60,
        maximum_characters_per_request: int = 40_000,
    ) -> None:
        if maximum_segments_per_request < 1:
            raise ValueError("Maximum segments per request must be positive.")
        if maximum_characters_per_request < 1:
            raise ValueError("Maximum characters per request must be positive.")

        self._provider = provider
        self._qualitative_instructions = qualitative_instructions
        self._company_policy = company_policy
        self._maximum_segments_per_request = maximum_segments_per_request
        self._maximum_characters_per_request = maximum_characters_per_request

    def check_connection(self) -> SemanticProviderConnection:
        """Exercise authentication, model access and structured output."""

        self._provider.extract(
            SemanticExtractionRequest(
                document_id="provider_connection_check",
                catalog_id="provider_connection_check",
                catalog_version="1",
                metrics=(
                    MetricInstruction(
                        indicator_id="connection_check_metric",
                        name="Connection check metric",
                        aliases=("connection check metric",),
                        canonical_unit="percent",
                        accepted_unit_aliases=("percent",),
                        minimum=0,
                        maximum=100,
                    ),
                ),
                segments=(
                    SemanticSourceSegment(
                        segment_id="connection_check_segment",
                        page_number=1,
                        locator="connection check",
                        text=(
                            "This is a provider connection check. It contains "
                            "no environmental measurement."
                        ),
                    ),
                ),
            )
        )
        return SemanticProviderConnection(
            provider_name=self._provider.provider_name,
            provider_version=self._provider.provider_version,
            model_name=self._provider.model_name,
        )

    def extract(
        self,
        *,
        document: SourceDocument,
        extracted_document: ExtractedDocument,
        catalog: MetricCatalog,
    ) -> IntelligentExtractionReport:
        """Extract, verify and convert intelligent claims."""

        if (
            extracted_document.document_id
            != document.document_id
        ):
            raise ValueError(
                "Extracted content belongs to a different "
                "document."
            )

        request = _build_request(
            extracted_document=extracted_document,
            catalog=catalog,
            qualitative_instructions=self._qualitative_instructions,
            company_policy=self._company_policy,
        )
        requests = _partition_request(
            request,
            maximum_segments=self._maximum_segments_per_request,
            maximum_characters=self._maximum_characters_per_request,
        )
        metrics = {
            metric.indicator_id: metric
            for metric in catalog.metrics
        }
        qualitative = {
            instruction.claim_id: instruction
            for instruction in self._qualitative_instructions
        }
        document_type_ids = {
            item.document_type_id
            for item in (
                self._company_policy.document_types
                if self._company_policy
                else ()
            )
        }
        company_field_ids = {
            item.field_id
            for item in (
                self._company_policy.company_profile_fields
                if self._company_policy
                else ()
            )
        }
        sector_ids = {
            item.sector_id
            for item in (
                self._company_policy.sectors
                if self._company_policy
                else ()
            )
        }
        activity_fact_ids = set(request.activity_fact_ids)
        unmapped_category_ids = {
            item.category_id
            for item in (
                self._company_policy.unmapped_material_categories
                if self._company_policy
                else ()
            )
        }

        evidence_items: list[EvidenceItem] = []
        intelligence_claims: list[GroundedIntelligenceClaim] = []
        rejected_claims: list[RejectedSemanticClaim] = []

        claim_index = 0

        _LOGGER.info(
            "Semantic extraction started for document %s using %s/%s in %s request(s).",
            document.document_id,
            self._provider.provider_name,
            self._provider.model_name,
            len(requests),
        )

        for bounded_request in requests:
            provider_output = self._provider.extract(bounded_request)
            segments = {
                segment.segment_id: segment
                for segment in bounded_request.segments
            }

            for claim in provider_output.claims:
                result = _ground_claim(
                    claim=claim,
                    document=document,
                    segments=segments,
                    metrics=metrics,
                    provider_name=self._provider.provider_name,
                    provider_version=self._provider.provider_version,
                    model_name=self._provider.model_name,
                )
                _append_result(
                    result=result,
                    claim_index=claim_index,
                    indicator_id=claim.indicator_id,
                    segment_id=claim.segment_id,
                    evidence_items=evidence_items,
                    rejected_claims=rejected_claims,
                )
                claim_index += 1

            for claim in provider_output.qualitative_claims:
                result = _ground_qualitative_claim(
                    claim=claim,
                    document=document,
                    segments=segments,
                    instructions=qualitative,
                    provider_name=self._provider.provider_name,
                    provider_version=self._provider.provider_version,
                    model_name=self._provider.model_name,
                )
                _append_result(
                    result=result,
                    claim_index=claim_index,
                    indicator_id=claim.claim_id,
                    segment_id=claim.segment_id,
                    evidence_items=evidence_items,
                    rejected_claims=rejected_claims,
                )
                claim_index += 1

            for claim in provider_output.document_profile_claims:
                result = _ground_document_profile_claim(
                    claim=claim,
                    document=document,
                    segments=segments,
                    allowed_ids=document_type_ids,
                )
                _append_intelligence_result(
                    result=result,
                    claim_index=claim_index,
                    indicator_id=f"document_profile:{claim.document_type_id}",
                    segment_id=claim.segment_id,
                    intelligence_claims=intelligence_claims,
                    rejected_claims=rejected_claims,
                )
                claim_index += 1

            for claim in provider_output.company_profile_claims:
                result = _ground_company_profile_claim(
                    claim=claim,
                    document=document,
                    segments=segments,
                    allowed_ids=company_field_ids,
                )
                _append_intelligence_result(
                    result=result,
                    claim_index=claim_index,
                    indicator_id=f"company_profile:{claim.field_id}",
                    segment_id=claim.segment_id,
                    intelligence_claims=intelligence_claims,
                    rejected_claims=rejected_claims,
                )
                claim_index += 1

            for claim in provider_output.sector_activity_proposals:
                result = _ground_sector_activity_proposal(
                    claim=claim,
                    document=document,
                    segments=segments,
                    allowed_sector_ids=sector_ids,
                    allowed_activity_fact_ids=activity_fact_ids,
                )
                _append_intelligence_result(
                    result=result,
                    claim_index=claim_index,
                    indicator_id=f"sector_activity:{claim.sector_id}",
                    segment_id=claim.segment_id,
                    intelligence_claims=intelligence_claims,
                    rejected_claims=rejected_claims,
                )
                claim_index += 1

            for claim in provider_output.unmapped_material_claims:
                result = _ground_unmapped_material_claim(
                    claim=claim,
                    document=document,
                    segments=segments,
                    allowed_ids=unmapped_category_ids,
                )
                _append_intelligence_result(
                    result=result,
                    claim_index=claim_index,
                    indicator_id=f"unmapped_material:{claim.category_id}",
                    segment_id=claim.segment_id,
                    intelligence_claims=intelligence_claims,
                    rejected_claims=rejected_claims,
                )
                claim_index += 1

        unique_evidence = {
            item.evidence_id: item for item in evidence_items
        }
        unique_intelligence = tuple(
            {
                claim.claim_id: claim
                for claim in intelligence_claims
            }.values()
        )
        limited_intelligence = _limit_unmapped_claims(
            unique_intelligence,
            maximum=(
                self._company_policy.maximum_unmapped_claims_per_document
                if self._company_policy
                else 0
            ),
        )

        _LOGGER.info(
            "Semantic extraction completed for document %s: %s evidence item(s), "
            "%s rejected claim(s).",
            document.document_id,
            len(unique_evidence),
            len(rejected_claims),
        )

        return IntelligentExtractionReport(
            provider_name=self._provider.provider_name,
            provider_version=(
                self._provider.provider_version
            ),
            model_name=self._provider.model_name,
            request_count=len(requests),
            company_policy_id=(
                self._company_policy.policy_id if self._company_policy else None
            ),
            company_policy_version=(
                self._company_policy.version if self._company_policy else None
            ),
            evidence_items=tuple(unique_evidence.values()),
            intelligence_claims=limited_intelligence,
            rejected_claims=tuple(rejected_claims),
        )


def _build_request(
    *,
    extracted_document: ExtractedDocument,
    catalog: MetricCatalog,
    qualitative_instructions: tuple[QualitativeInstruction, ...] = (),
    company_policy: CompanyIntelligencePolicy | None = None,
) -> SemanticExtractionRequest:
    """Build a bounded request from structured document regions."""

    segments = tuple(
        segment
        for page in extracted_document.pages
        for segment in _page_segments(page)
    )

    if not segments:
        raise ValueError(
            "No readable source segments are available."
        )

    metrics = tuple(
        MetricInstruction(
            indicator_id=metric.indicator_id,
            name=metric.name,
            aliases=metric.aliases,
            canonical_unit=metric.canonical_unit,
            accepted_unit_aliases=tuple(
                alias
                for unit in metric.units
                for alias in unit.aliases
            ),
            minimum=metric.minimum,
            maximum=metric.maximum,
        )
        for metric in catalog.metrics
    )

    return SemanticExtractionRequest(
        document_id=extracted_document.document_id,
        catalog_id=catalog.catalog_id,
        catalog_version=catalog.version,
        metrics=metrics,
        qualitative_claims=qualitative_instructions,
        document_types=(company_policy.document_types if company_policy else ()),
        company_profile_fields=(
            company_policy.company_profile_fields if company_policy else ()
        ),
        sectors=(company_policy.sectors if company_policy else ()),
        activity_fact_ids=tuple(
            instruction.claim_id.removeprefix("activity_fact:")
            for instruction in qualitative_instructions
            if instruction.claim_id.startswith("activity_fact:")
        ),
        unmapped_material_categories=(
            company_policy.unmapped_material_categories if company_policy else ()
        ),
        maximum_unmapped_claims=(
            company_policy.maximum_unmapped_claims_per_document
            if company_policy
            else 0
        ),
        segments=segments,
    )


def _partition_request(
    request: SemanticExtractionRequest,
    *,
    maximum_segments: int,
    maximum_characters: int,
) -> tuple[SemanticExtractionRequest, ...]:
    """Split long content without breaking source segments."""

    batches: list[tuple[SemanticSourceSegment, ...]] = []
    current: list[SemanticSourceSegment] = []
    current_characters = 0

    for segment in request.segments:
        segment_characters = len(segment.text)
        would_overflow = current and (
            len(current) >= maximum_segments
            or current_characters + segment_characters > maximum_characters
        )

        if would_overflow:
            batches.append(tuple(current))
            current = []
            current_characters = 0

        current.append(segment)
        current_characters += segment_characters

    if current:
        batches.append(tuple(current))

    return tuple(
        request.model_copy(update={"segments": segments})
        for segments in batches
    )


def _page_segments(
    page: ExtractedPage,
) -> tuple[SemanticSourceSegment, ...]:
    """Create stable provider segments from page structure."""

    segments: list[SemanticSourceSegment] = []

    for block_index, block in enumerate(
        page.text_blocks,
        start=1,
    ):
        segments.append(
            SemanticSourceSegment(
                segment_id=(
                    f"page_{page.page_number}_"
                    f"block_{block_index}"
                ),
                page_number=page.page_number,
                locator=(
                    f"page {page.page_number}, "
                    f"block {block.block_id}"
                ),
                text=block.text,
            )
        )

    for table_index, table in enumerate(
        page.tables,
        start=1,
    ):
        matrix = table.as_matrix()
        header_text = " || ".join(
            " | ".join(
                value.strip()
                for value in matrix[index]
                if value.strip()
            )
            for index in table.header_row_indices
            if 0 <= index < len(matrix)
        )

        for row_index, row in enumerate(
            matrix,
            start=1,
        ):
            row_text = " | ".join(
                value.strip()
                for value in row
                if value.strip()
            )

            if not row_text:
                continue

            zero_based_row = row_index - 1
            text = (
                f"{header_text} || {row_text}"
                if header_text
                and zero_based_row not in table.header_row_indices
                else row_text
            )

            segments.append(
                SemanticSourceSegment(
                    segment_id=(
                        f"page_{page.page_number}_"
                        f"table_{table_index}_row_{row_index}"
                    ),
                    page_number=page.page_number,
                    locator=(
                        f"page {page.page_number}, "
                        f"table {table.table_id}, "
                        f"row {row_index}"
                    ),
                    text=text,
                )
            )

    if not segments:
        segments.append(
            SemanticSourceSegment(
                segment_id=f"page_{page.page_number}_text",
                page_number=page.page_number,
                locator=f"page {page.page_number}",
                text=page.text,
            )
        )

    return tuple(segments)


def _ground_claim(
    *,
    claim: SemanticClaimPayload,
    document: SourceDocument,
    segments: dict[str, SemanticSourceSegment],
    metrics: dict[str, MetricDefinition],
    provider_name: str,
    provider_version: str,
    model_name: str,
) -> EvidenceItem | str:
    """Return evidence or a precise rejection reason."""

    segment = segments.get(claim.segment_id)

    if segment is None:
        return "The claim references an unknown source segment."

    metric = metrics.get(claim.indicator_id)

    if metric is None:
        return "The claim references an unconfigured indicator."

    if not _contains_text(
        segment.text,
        claim.source_quote,
    ):
        return (
            "The source quote does not occur in the referenced "
            "segment."
        )

    if not _contains_text(
        claim.source_quote,
        claim.raw_value,
    ):
        return (
            "The raw value does not occur in the source quote."
        )

    if not _raw_unit_occurs_in_value(
        raw_value=claim.source_quote,
        raw_unit=claim.raw_unit,
    ):
        return (
            "The raw unit does not occur in the source quote."
        )

    if (
        claim.reporting_period is not None
        and not _contains_text(
            claim.source_quote,
            claim.reporting_period,
        )
    ):
        return (
            "The reporting period does not occur in the source quote."
        )

    if (
        claim.scope is not None
        and not _contains_text(
            claim.source_quote,
            claim.scope,
        )
    ):
        return "The scope does not occur in the source quote."

    unit_rule = _find_unit_rule(
        metric,
        claim.raw_unit,
    )

    if unit_rule is None:
        return (
            "The raw unit is not allowed for this indicator."
        )

    normalized_value = (
        claim.raw_number * unit_rule.multiplier
    )
    reporting_period = (
        normalize_reporting_period(claim.reporting_period)
        if claim.reporting_period is not None
        else None
    )
    scope = (
        normalize_scope(claim.scope)
        if claim.scope is not None
        else None
    )

    if (
        metric.minimum is not None
        and normalized_value < metric.minimum
    ):
        return (
            "The normalized value is below the metric minimum."
        )

    if (
        metric.maximum is not None
        and normalized_value > metric.maximum
    ):
        return (
            "The normalized value exceeds the metric maximum."
        )

    if not _raw_number_occurs_in_value(
        raw_number=claim.raw_number,
        raw_value=claim.raw_value,
    ):
        return (
            "The structured raw number does not match the number "
            "written in the raw value."
        )

    fingerprint = sha256(
        (
            f"{document.document_id}:"
            f"{claim.segment_id}:"
            f"{claim.indicator_id}:"
            f"{claim.raw_value}:"
            f"{normalized_value}:"
            f"{unit_rule.canonical_unit}:"
            f"{reporting_period}:"
            f"{scope}:"
            f"{provider_name}:"
            f"{model_name}"
        ).encode()
    ).hexdigest()[:20]

    return EvidenceItem(
        evidence_id=f"evidence_{fingerprint}",
        sme_id=document.sme_id,
        document_id=document.document_id,
        indicator_id=metric.indicator_id,
        criterion_id=metric.criterion_id,
        raw_value=claim.raw_value,
        normalized_value=normalized_value,
        unit=unit_rule.canonical_unit,
        source_locator=segment.locator,
        source_excerpt=claim.source_quote,
        extraction_method=(
            "language_model_structured_extraction"
        ),
        extractor_name=(
            f"{provider_name}:{model_name}"
        ),
        extractor_version=provider_version,
        confidence=None,
        reporting_period=reporting_period,
        scope=scope,
    )


def _ground_qualitative_claim(
    *,
    claim: QualitativeClaimPayload,
    document: SourceDocument,
    segments: dict[str, SemanticSourceSegment],
    instructions: dict[str, QualitativeInstruction],
    provider_name: str,
    provider_version: str,
    model_name: str,
) -> EvidenceItem | str:
    """Ground a context proposal without converting it into a score."""

    segment = segments.get(claim.segment_id)

    if segment is None:
        return "The claim references an unknown source segment."

    instruction = instructions.get(claim.claim_id)

    if instruction is None:
        return "The claim references an unconfigured qualitative claim."

    if not _contains_text(segment.text, claim.source_quote):
        return "The source quote does not occur in the referenced segment."

    if (
        claim.reporting_period is not None
        and not _contains_text(claim.source_quote, claim.reporting_period)
    ):
        return "The reporting period does not occur in the source quote."

    if claim.scope is not None and not _contains_text(
        claim.source_quote,
        claim.scope,
    ):
        return "The scope does not occur in the source quote."

    if instruction.value_type is QualitativeValueType.BOOLEAN:
        if claim.boolean_value is None:
            return "The configured activity fact requires a boolean value."
        normalized_value: str | bool = claim.boolean_value
    else:
        if claim.boolean_value is not None:
            return "A source-text claim must not contain a boolean value."
        normalized_value = claim.source_quote

    reporting_period = (
        normalize_reporting_period(claim.reporting_period)
        if claim.reporting_period is not None
        else None
    )
    scope = (
        normalize_scope(claim.scope)
        if claim.scope is not None
        else None
    )
    fingerprint = sha256(
        (
            f"{document.document_id}:{claim.segment_id}:"
            f"{claim.claim_id}:{claim.source_quote}:"
            f"{normalized_value}:{reporting_period}:{scope}:"
            f"{provider_name}:{model_name}"
        ).encode()
    ).hexdigest()[:20]

    return EvidenceItem(
        evidence_id=f"evidence_{fingerprint}",
        sme_id=document.sme_id,
        document_id=document.document_id,
        indicator_id=claim.claim_id,
        # Narrative and activity facts support assessment preparation, but
        # are deliberately not treated as scored criterion observations.
        criterion_id=None,
        raw_value=claim.source_quote,
        normalized_value=normalized_value,
        unit=None,
        source_locator=segment.locator,
        source_excerpt=claim.source_quote,
        extraction_method="language_model_grounded_context_extraction",
        extractor_name=f"{provider_name}:{model_name}",
        extractor_version=provider_version,
        confidence=None,
        reporting_period=reporting_period,
        scope=scope,
    )


def _ground_document_profile_claim(
    *,
    claim: DocumentProfileClaimPayload,
    document: SourceDocument,
    segments: dict[str, SemanticSourceSegment],
    allowed_ids: set[str],
) -> GroundedIntelligenceClaim | str:
    """Ground a controlled document-type proposal."""

    segment = segments.get(claim.segment_id)
    if segment is None:
        return "The claim references an unknown source segment."
    if claim.document_type_id not in allowed_ids:
        return "The claim references an unconfigured document type."
    if not _contains_text(segment.text, claim.source_quote):
        return "The source quote does not occur in the referenced segment."

    optional_values = (
        claim.issuer_name,
        claim.reporting_period,
        claim.assurance_status,
    )
    if any(
        value is not None and not _contains_text(claim.source_quote, value)
        for value in optional_values
    ):
        return "Document-profile detail does not occur in the source quote."

    return _intelligence_claim(
        document=document,
        segment=segment,
        segment_id=claim.segment_id,
        claim_type="document_profile",
        field_id="document_type",
        value=claim.document_type_id,
        source_quote=claim.source_quote,
    )


def _ground_company_profile_claim(
    *,
    claim: CompanyProfileClaimPayload,
    document: SourceDocument,
    segments: dict[str, SemanticSourceSegment],
    allowed_ids: set[str],
) -> GroundedIntelligenceClaim | str:
    """Ground a company fact without promoting it to master data."""

    segment = segments.get(claim.segment_id)
    if segment is None:
        return "The claim references an unknown source segment."
    if claim.field_id not in allowed_ids:
        return "The claim references an unconfigured company-profile field."
    if not _contains_text(segment.text, claim.source_quote):
        return "The source quote does not occur in the referenced segment."
    if not _contains_text(claim.source_quote, claim.raw_value):
        return "The company-profile value does not occur in the source quote."

    return _intelligence_claim(
        document=document,
        segment=segment,
        segment_id=claim.segment_id,
        claim_type="company_profile",
        field_id=claim.field_id,
        value=claim.raw_value,
        source_quote=claim.source_quote,
    )


def _ground_sector_activity_proposal(
    *,
    claim: SectorActivityProposalPayload,
    document: SourceDocument,
    segments: dict[str, SemanticSourceSegment],
    allowed_sector_ids: set[str],
    allowed_activity_fact_ids: set[str],
) -> GroundedIntelligenceClaim | str:
    """Ground a sector interpretation against controlled vocabularies."""

    segment = segments.get(claim.segment_id)
    if segment is None:
        return "The claim references an unknown source segment."
    if claim.sector_id not in allowed_sector_ids:
        return "The claim references an unconfigured sector."
    if any(
        activity_id not in allowed_activity_fact_ids
        for activity_id in claim.activity_fact_ids
    ):
        return "The claim references an unconfigured activity fact."
    if not _contains_text(segment.text, claim.source_quote):
        return "The source quote does not occur in the referenced segment."

    return _intelligence_claim(
        document=document,
        segment=segment,
        segment_id=claim.segment_id,
        claim_type="sector_activity_proposal",
        field_id="sector",
        value=claim.sector_id,
        source_quote=claim.source_quote,
        related_ids=claim.activity_fact_ids,
    )


def _ground_unmapped_material_claim(
    *,
    claim: UnmappedMaterialClaimPayload,
    document: SourceDocument,
    segments: dict[str, SemanticSourceSegment],
    allowed_ids: set[str],
) -> GroundedIntelligenceClaim | str:
    """Ground review-only material outside the assessment schema."""

    segment = segments.get(claim.segment_id)
    if segment is None:
        return "The claim references an unknown source segment."
    if claim.category_id not in allowed_ids:
        return "The claim references an unconfigured unmapped category."
    if not _contains_text(segment.text, claim.source_quote):
        return "The source quote does not occur in the referenced segment."

    return _intelligence_claim(
        document=document,
        segment=segment,
        segment_id=claim.segment_id,
        claim_type="unmapped_material",
        field_id=claim.category_id,
        value=claim.suggested_label,
        source_quote=claim.source_quote,
        model_rationale=claim.model_rationale,
    )


def _intelligence_claim(
    *,
    document: SourceDocument,
    segment: SemanticSourceSegment,
    segment_id: str,
    claim_type: str,
    field_id: str,
    value: str,
    source_quote: str,
    related_ids: tuple[str, ...] = (),
    model_rationale: str | None = None,
) -> GroundedIntelligenceClaim:
    """Build a stable, traceable non-scoring intelligence claim."""

    fingerprint = sha256(
        (
            f"{document.document_id}:{segment_id}:{claim_type}:"
            f"{field_id}:{value}:{source_quote}:{related_ids}"
        ).encode()
    ).hexdigest()[:20]
    return GroundedIntelligenceClaim(
        claim_id=f"intelligence_{fingerprint}",
        claim_type=claim_type,
        field_id=field_id,
        value=value,
        source_locator=segment.locator,
        source_quote=source_quote,
        related_ids=related_ids,
        model_rationale=model_rationale,
    )


def _append_intelligence_result(
    *,
    result: GroundedIntelligenceClaim | str,
    claim_index: int,
    indicator_id: str,
    segment_id: str,
    intelligence_claims: list[GroundedIntelligenceClaim],
    rejected_claims: list[RejectedSemanticClaim],
) -> None:
    """Collect a grounded intelligence proposal or rejection."""

    if isinstance(result, GroundedIntelligenceClaim):
        intelligence_claims.append(result)
        return

    rejected_claims.append(
        RejectedSemanticClaim(
            claim_index=claim_index,
            indicator_id=indicator_id,
            segment_id=segment_id,
            reason=result,
        )
    )


def _limit_unmapped_claims(
    claims: tuple[GroundedIntelligenceClaim, ...],
    *,
    maximum: int,
) -> tuple[GroundedIntelligenceClaim, ...]:
    """Apply the document-level safety cap without dropping governed claims."""

    unmapped_count = 0
    result: list[GroundedIntelligenceClaim] = []
    for claim in claims:
        if claim.claim_type == "unmapped_material":
            if unmapped_count >= maximum:
                continue
            unmapped_count += 1
        result.append(claim)
    return tuple(result)


def _append_result(
    *,
    result: EvidenceItem | str,
    claim_index: int,
    indicator_id: str,
    segment_id: str,
    evidence_items: list[EvidenceItem],
    rejected_claims: list[RejectedSemanticClaim],
) -> None:
    """Collect a grounded proposal or its explicit rejection."""

    if isinstance(result, EvidenceItem):
        evidence_items.append(result)
        return

    rejected_claims.append(
        RejectedSemanticClaim(
            claim_index=claim_index,
            indicator_id=indicator_id,
            segment_id=segment_id,
            reason=result,
        )
    )


def _find_unit_rule(
    metric: MetricDefinition,
    raw_unit: str,
) -> UnitRule | None:
    """Resolve a provider unit using configured aliases."""

    normalized_unit = _normalize_text(raw_unit)

    for unit_rule in metric.units:
        if any(
            _normalize_text(alias) == normalized_unit
            for alias in unit_rule.aliases
        ):
            return unit_rule

    return None


def _contains_text(
    container: str,
    candidate: str,
) -> bool:
    """Compare text despite harmless spacing differences."""

    return _normalize_text(candidate) in _normalize_text(
        container
    )


def _raw_unit_occurs_in_value(
    *,
    raw_value: str,
    raw_unit: str,
) -> bool:
    """Allow scale words around a written number without weakening grounding."""

    normalized_value = _normalize_text(raw_value)
    normalized_unit = _normalize_text(raw_unit)

    if normalized_unit in normalized_value:
        return True

    unit_tokens = tuple(
        token
        for token in re.findall(r"[a-z0-9%³]+", normalized_unit)
        if token
    )
    value_tokens = set(re.findall(r"[a-z0-9%³]+", normalized_value))

    return bool(unit_tokens) and all(
        token in value_tokens for token in unit_tokens
    )


def _raw_number_occurs_in_value(
    *,
    raw_number: float,
    raw_value: str,
) -> bool:
    """Require the provider's number to be literally grounded in its value."""

    for match in _WRITTEN_NUMBER_PATTERN.finditer(raw_value):
        try:
            written_number = float(
                match.group().replace(",", "")
            )
        except ValueError:
            continue

        if isclose(
            written_number,
            raw_number,
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            return True

    return False


def _normalize_text(value: str) -> str:
    """Normalize spacing and case without changing meaning."""

    return " ".join(value.casefold().split())
