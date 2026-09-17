"""Domain models for the submitted-document processing lifecycle."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DocumentProcessingStatus(StrEnum):
    """Describe the current state of one submitted document."""

    STORED = "stored"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentProcessingState(BaseModel):
    """Expose durable progress and diagnostics for one document."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    document_id: str = Field(min_length=1)
    sme_id: str = Field(min_length=1)
    status: DocumentProcessingStatus
    attempt_count: int = Field(default=0, ge=0)

    evidence_count: int = Field(default=0, ge=0)
    deterministic_evidence_count: int = Field(default=0, ge=0)
    intelligent_evidence_count: int = Field(default=0, ge=0)
    rejected_intelligent_claim_count: int = Field(default=0, ge=0)
    intelligent_provider_status: str | None = Field(
        default=None,
        min_length=1,
    )

    failure_code: str | None = Field(default=None, min_length=1)
    failure_message: str | None = Field(default=None, min_length=1)

    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime

    @model_validator(mode="after")
    def validate_state(self) -> "DocumentProcessingState":
        """Keep status-specific fields internally consistent."""

        if self.status is DocumentProcessingStatus.STORED:
            if self.attempt_count != 0:
                raise ValueError(
                    "Stored documents must not contain processing attempts."
                )

        if self.status is DocumentProcessingStatus.PROCESSING:
            if self.attempt_count < 1 or self.started_at is None:
                raise ValueError(
                    "Processing documents require an active attempt."
                )

        if self.status is DocumentProcessingStatus.COMPLETED:
            if self.attempt_count < 1 or self.completed_at is None:
                raise ValueError(
                    "Completed documents require completion metadata."
                )

            if self.failure_code is not None or self.failure_message is not None:
                raise ValueError(
                    "Completed documents must not contain failure details."
                )

        if self.status is DocumentProcessingStatus.FAILED:
            if (
                self.attempt_count < 1
                or self.completed_at is None
                or self.failure_code is None
                or self.failure_message is None
            ):
                raise ValueError(
                    "Failed documents require complete failure metadata."
                )

        return self
