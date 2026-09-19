"""Durable jobs for asynchronous document processing."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DocumentJobStatus(StrEnum):
    """Describe the lifecycle of a queued processing job."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentProcessingJob(BaseModel):
    """Expose durable, retryable work for one submitted document."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    job_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    sme_id: str = Field(min_length=1)
    requested_by: str = Field(min_length=1)
    status: DocumentJobStatus
    attempt_count: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1, le=10)
    failure_code: str | None = Field(default=None, min_length=1)
    failure_message: str | None = Field(default=None, min_length=1)
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime

    @model_validator(mode="after")
    def validate_lifecycle(self) -> "DocumentProcessingJob":
        """Keep status-specific timestamps and diagnostics coherent."""

        if self.attempt_count > self.max_attempts:
            raise ValueError("Job attempts must not exceed the retry limit.")

        if self.status is DocumentJobStatus.QUEUED:
            if self.started_at is not None or self.completed_at is not None:
                raise ValueError("Queued jobs cannot have execution timestamps.")

        if self.status is DocumentJobStatus.RUNNING:
            if self.attempt_count < 1 or self.started_at is None:
                raise ValueError("Running jobs require an active attempt.")

            if self.completed_at is not None:
                raise ValueError("Running jobs cannot be completed.")

        if self.status is DocumentJobStatus.COMPLETED:
            if self.attempt_count < 1 or self.completed_at is None:
                raise ValueError("Completed jobs require execution metadata.")

            if self.failure_code is not None or self.failure_message is not None:
                raise ValueError("Completed jobs cannot retain a failure.")

        if self.status is DocumentJobStatus.FAILED:
            if (
                self.attempt_count < 1
                or self.completed_at is None
                or self.failure_code is None
                or self.failure_message is None
            ):
                raise ValueError("Failed jobs require complete diagnostics.")

        return self
