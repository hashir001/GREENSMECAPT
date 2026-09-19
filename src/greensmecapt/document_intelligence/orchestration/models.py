"""Plans and diagnostics for bounded document processing."""

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from greensmecapt.document_intelligence.models import TextSource


class DocumentExecutionMode(StrEnum):
    """Describe whether processing belongs in the request or a worker."""

    IMMEDIATE = "immediate"
    BACKGROUND = "background"


class PageContentKind(StrEnum):
    """Describe content that affects a page's processing route."""

    DIGITAL_TEXT = "digital_text"
    SCANNED_TEXT = "scanned_text"
    TABLE = "table"
    CHART = "chart"
    DIAGRAM = "diagram"
    IMAGE = "image"
    UNKNOWN = "unknown"


class ProcessingCapability(StrEnum):
    """Describe a processor or review step required by a page."""

    NATIVE_READING = "native_reading"
    OCR = "ocr"
    TABLE_STRUCTURE = "table_structure"
    MULTIMODAL_INTERPRETATION = "multimodal_interpretation"
    VISUAL_RELEVANCE_REVIEW = "visual_relevance_review"
    HUMAN_REVIEW = "human_review"


class BatchStatus(StrEnum):
    """Describe durable progress for one bounded group of pages."""

    PLANNED = "planned"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class OrchestrationModel(BaseModel):
    """Strict immutable base for processing-plan models."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class LongDocumentPolicy(OrchestrationModel):
    """Control immediate work, page batching and bounded retries."""

    immediate_page_limit: int = Field(default=10, ge=1)
    page_batch_size: int = Field(default=10, ge=1, le=100)
    maximum_batch_attempts: int = Field(default=3, ge=1, le=10)
    immediate_multimodal_region_limit: int = Field(default=2, ge=0)


class PageProcessingProfile(OrchestrationModel):
    """Record what one page contains and what it requires."""

    page_number: int = Field(ge=1)
    text_source: TextSource | None = None
    content_kinds: tuple[PageContentKind, ...] = Field(min_length=1)
    required_capabilities: tuple[ProcessingCapability, ...] = Field(
        min_length=1
    )
    table_count: int = Field(default=0, ge=0)
    visual_region_count: int = Field(default=0, ge=0)
    reasons: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_values(self) -> Self:
        """Prevent repeated classifications and routing requirements."""

        if len(self.content_kinds) != len(set(self.content_kinds)):
            raise ValueError("Page content kinds must be unique.")

        if len(self.required_capabilities) != len(
            set(self.required_capabilities)
        ):
            raise ValueError(
                "Page processing capabilities must be unique."
            )

        return self


class PageProcessingBatch(OrchestrationModel):
    """Represent one retryable, checkpointable unit of page work."""

    batch_id: str = Field(min_length=1)
    page_numbers: tuple[int, ...] = Field(min_length=1)
    status: BatchStatus = BatchStatus.PLANNED
    attempt_count: int = Field(default=0, ge=0)
    maximum_attempts: int = Field(default=3, ge=1)
    failure_message: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_batch_state(self) -> Self:
        """Keep page order, retries and failure diagnostics consistent."""

        if list(self.page_numbers) != sorted(self.page_numbers):
            raise ValueError("Batch pages must follow source order.")

        if len(self.page_numbers) != len(set(self.page_numbers)):
            raise ValueError("Batch page numbers must be unique.")

        if self.attempt_count > self.maximum_attempts:
            raise ValueError("Batch attempts exceed the configured maximum.")

        if self.status is BatchStatus.PLANNED and self.attempt_count != 0:
            raise ValueError("Planned batches cannot contain attempts.")

        if self.status is BatchStatus.PROCESSING and self.attempt_count < 1:
            raise ValueError("Processing batches require an attempt.")

        if self.status is BatchStatus.FAILED and self.failure_message is None:
            raise ValueError("Failed batches require a failure message.")

        if self.status is not BatchStatus.FAILED and (
            self.failure_message is not None
        ):
            raise ValueError(
                "Only failed batches may contain a failure message."
            )

        return self


class DocumentProcessingManifest(OrchestrationModel):
    """Describe bounded execution and page-level routing for a document."""

    document_id: str = Field(min_length=1)
    total_pages: int = Field(ge=1)
    execution_mode: DocumentExecutionMode
    page_profiles: tuple[PageProcessingProfile, ...] = Field(min_length=1)
    batches: tuple[PageProcessingBatch, ...] = Field(min_length=1)
    unreadable_pages: tuple[int, ...] = ()
    table_page_count: int = Field(default=0, ge=0)
    visual_page_count: int = Field(default=0, ge=0)
    multimodal_page_count: int = Field(default=0, ge=0)
    review_required_page_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_document_coverage(self) -> Self:
        """Require one profile and one batch assignment for every page."""

        expected_pages = set(range(1, self.total_pages + 1))
        profile_pages = [
            profile.page_number for profile in self.page_profiles
        ]
        batched_pages = [
            page_number
            for batch in self.batches
            for page_number in batch.page_numbers
        ]

        if len(profile_pages) != len(set(profile_pages)):
            raise ValueError("Page profiles must have unique page numbers.")

        if set(profile_pages) != expected_pages:
            raise ValueError("Page profiles must cover the whole document.")

        if len(batched_pages) != len(set(batched_pages)):
            raise ValueError("A page may belong to only one batch.")

        if set(batched_pages) != expected_pages:
            raise ValueError("Page batches must cover the whole document.")

        if set(self.unreadable_pages) - expected_pages:
            raise ValueError("Unreadable page number exceeds total pages.")

        return self
