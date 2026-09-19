"""Classify document pages and produce bounded execution plans."""

from greensmecapt.document_intelligence.models import (
    ExtractedDocument,
    ExtractedPage,
    TextSource,
    VisualRegionKind,
)
from greensmecapt.document_intelligence.orchestration.models import (
    DocumentExecutionMode,
    DocumentProcessingManifest,
    LongDocumentPolicy,
    PageContentKind,
    PageProcessingBatch,
    PageProcessingProfile,
    ProcessingCapability,
)


class DocumentProcessingPlanner:
    """Map recovered content to processors without inspecting whole files twice."""

    def __init__(
        self,
        policy: LongDocumentPolicy | None = None,
    ) -> None:
        self._policy = policy or LongDocumentPolicy()

    def plan(
        self,
        document: ExtractedDocument,
    ) -> DocumentProcessingManifest:
        """Return page classifications and retryable batches."""

        total_pages = document.total_pages or max(
            page.page_number for page in document.pages
        )
        readable_pages = {
            page.page_number: page
            for page in document.pages
        }
        unreadable_pages = set(document.unreadable_pages)
        profiles = tuple(
            self._profile_page(
                page_number=page_number,
                page=readable_pages.get(page_number),
                unreadable=(page_number in unreadable_pages),
            )
            for page_number in range(1, total_pages + 1)
        )
        batches = tuple(
            PageProcessingBatch(
                batch_id=(
                    f"{document.document_id}_batch_"
                    f"{batch_index}"
                ),
                page_numbers=tuple(
                    range(
                        start_page,
                        min(
                            start_page + self._policy.page_batch_size,
                            total_pages + 1,
                        ),
                    )
                ),
                maximum_attempts=(
                    self._policy.maximum_batch_attempts
                ),
            )
            for batch_index, start_page in enumerate(
                range(
                    1,
                    total_pages + 1,
                    self._policy.page_batch_size,
                ),
                start=1,
            )
        )
        multimodal_pages = sum(
            ProcessingCapability.MULTIMODAL_INTERPRETATION
            in profile.required_capabilities
            for profile in profiles
        )
        execution_mode = (
            DocumentExecutionMode.BACKGROUND
            if (
                total_pages > self._policy.immediate_page_limit
                or multimodal_pages
                > self._policy.immediate_multimodal_region_limit
            )
            else DocumentExecutionMode.IMMEDIATE
        )

        return DocumentProcessingManifest(
            document_id=document.document_id,
            total_pages=total_pages,
            execution_mode=execution_mode,
            page_profiles=profiles,
            batches=batches,
            unreadable_pages=document.unreadable_pages,
            table_page_count=sum(
                PageContentKind.TABLE in profile.content_kinds
                for profile in profiles
            ),
            visual_page_count=sum(
                any(
                    kind
                    in {
                        PageContentKind.CHART,
                        PageContentKind.DIAGRAM,
                        PageContentKind.IMAGE,
                    }
                    for kind in profile.content_kinds
                )
                for profile in profiles
            ),
            multimodal_page_count=multimodal_pages,
            review_required_page_count=sum(
                any(
                    capability
                    in {
                        ProcessingCapability.HUMAN_REVIEW,
                        ProcessingCapability.VISUAL_RELEVANCE_REVIEW,
                    }
                    for capability in profile.required_capabilities
                )
                for profile in profiles
            ),
        )

    def _profile_page(
        self,
        *,
        page_number: int,
        page: ExtractedPage | None,
        unreadable: bool,
    ) -> PageProcessingProfile:
        """Classify one page from preserved extraction diagnostics."""

        if page is None or unreadable:
            return PageProcessingProfile(
                page_number=page_number,
                content_kinds=(PageContentKind.UNKNOWN,),
                required_capabilities=(
                    ProcessingCapability.HUMAN_REVIEW,
                ),
                reasons=(
                    "No processor recovered readable page content.",
                ),
            )

        content_kinds: list[PageContentKind] = []
        capabilities: list[ProcessingCapability] = []
        reasons: list[str] = []

        if page.text_source is TextSource.PDF_EMBEDDED:
            content_kinds.append(PageContentKind.DIGITAL_TEXT)
            capabilities.append(ProcessingCapability.NATIVE_READING)
            reasons.append("Embedded PDF text was recovered directly.")
        elif page.text_source is TextSource.PLAIN_TEXT:
            content_kinds.append(PageContentKind.DIGITAL_TEXT)
            capabilities.append(ProcessingCapability.NATIVE_READING)
            reasons.append("Born-digital text was decoded directly.")
        elif page.text_source is TextSource.OCR:
            content_kinds.append(PageContentKind.SCANNED_TEXT)
            capabilities.append(ProcessingCapability.OCR)
            reasons.append("Page text was recovered through OCR.")
        else:
            content_kinds.extend(
                (
                    PageContentKind.DIGITAL_TEXT,
                    PageContentKind.SCANNED_TEXT,
                )
            )
            capabilities.extend(
                (
                    ProcessingCapability.NATIVE_READING,
                    ProcessingCapability.OCR,
                )
            )
            reasons.append("Native and OCR content were combined.")

        if page.tables:
            content_kinds.append(PageContentKind.TABLE)
            capabilities.append(ProcessingCapability.TABLE_STRUCTURE)
            reasons.append(
                f"{len(page.tables)} structured table(s) were recovered."
            )

        for region in page.visual_regions:
            if region.kind is VisualRegionKind.CHART:
                content_kinds.append(PageContentKind.CHART)
                capabilities.append(
                    ProcessingCapability.MULTIMODAL_INTERPRETATION
                )
                reasons.append(
                    "A chart region requires selective visual interpretation."
                )
            elif region.kind is VisualRegionKind.DIAGRAM:
                content_kinds.append(PageContentKind.DIAGRAM)
                capabilities.append(
                    ProcessingCapability.MULTIMODAL_INTERPRETATION
                )
                reasons.append(
                    "A diagram region requires selective visual interpretation."
                )
            elif region.kind is not VisualRegionKind.LOGO:
                content_kinds.append(PageContentKind.IMAGE)
                capabilities.append(
                    ProcessingCapability.VISUAL_RELEVANCE_REVIEW
                )
                reasons.append(
                    "An image region must be checked for assessment relevance."
                )

        return PageProcessingProfile(
            page_number=page_number,
            text_source=page.text_source,
            content_kinds=_unique(content_kinds),
            required_capabilities=_unique(capabilities),
            table_count=len(page.tables),
            visual_region_count=len(page.visual_regions),
            reasons=tuple(reasons),
        )


def _unique(values):
    """Preserve stable order while removing enum duplicates."""

    return tuple(dict.fromkeys(values))
