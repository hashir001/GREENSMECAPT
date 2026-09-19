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


class DocumentBatchStatus(StrEnum):
    """Describe durable progress for one bounded page batch."""

    PLANNED = "planned"
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
    worker_id: str | None = Field(default=None, min_length=1)
    lease_expires_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
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

            if self.worker_id is not None or self.lease_expires_at is not None:
                raise ValueError("Queued jobs cannot be leased.")

        if self.status is DocumentJobStatus.RUNNING:
            if self.attempt_count < 1 or self.started_at is None:
                raise ValueError("Running jobs require an active attempt.")

            if self.completed_at is not None:
                raise ValueError("Running jobs cannot be completed.")

            if (
                self.worker_id is None
                or self.lease_expires_at is None
                or self.last_heartbeat_at is None
            ):
                raise ValueError("Running jobs require an active worker lease.")

        if self.status is DocumentJobStatus.COMPLETED:
            if self.attempt_count < 1 or self.completed_at is None:
                raise ValueError("Completed jobs require execution metadata.")

            if self.failure_code is not None or self.failure_message is not None:
                raise ValueError("Completed jobs cannot retain a failure.")

        if self.status is not DocumentJobStatus.RUNNING and (
            self.worker_id is not None
            or self.lease_expires_at is not None
            or self.last_heartbeat_at is not None
        ):
            raise ValueError("Only running jobs may retain a worker lease.")

        if self.status is DocumentJobStatus.FAILED:
            if (
                self.attempt_count < 1
                or self.completed_at is None
                or self.failure_code is None
                or self.failure_message is None
            ):
                raise ValueError("Failed jobs require complete diagnostics.")

        return self


class DocumentBatchCheckpoint(BaseModel):
    """Persist one resumable group of source-document pages."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    checkpoint_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    batch_id: str = Field(min_length=1)
    page_numbers: tuple[int, ...] = Field(min_length=1)
    status: DocumentBatchStatus = DocumentBatchStatus.PLANNED
    attempt_count: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1, le=10)
    worker_id: str | None = Field(default=None, min_length=1)
    failure_message: str | None = Field(default=None, min_length=1)
    result_json: str | None = Field(default=None, min_length=1)
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime

    @model_validator(mode="after")
    def validate_checkpoint(self) -> "DocumentBatchCheckpoint":
        """Keep page order, ownership and checkpoint output coherent."""

        if tuple(sorted(self.page_numbers)) != self.page_numbers:
            raise ValueError("Checkpoint pages must follow source order.")

        if len(self.page_numbers) != len(set(self.page_numbers)):
            raise ValueError("Checkpoint page numbers must be unique.")

        if self.attempt_count > self.max_attempts:
            raise ValueError("Checkpoint attempts exceed the retry limit.")

        if self.status is DocumentBatchStatus.PLANNED:
            if self.attempt_count != 0 or self.worker_id is not None:
                raise ValueError("Planned checkpoints cannot have a worker.")

        if self.status is DocumentBatchStatus.RUNNING:
            if (
                self.attempt_count < 1
                or self.worker_id is None
                or self.started_at is None
            ):
                raise ValueError("Running checkpoints require an owner.")

        if self.status is DocumentBatchStatus.COMPLETED:
            if self.completed_at is None or self.result_json is None:
                raise ValueError("Completed checkpoints require saved output.")

        if self.status is DocumentBatchStatus.FAILED:
            if self.completed_at is None or self.failure_message is None:
                raise ValueError("Failed checkpoints require diagnostics.")

        if self.status is not DocumentBatchStatus.RUNNING and (
            self.worker_id is not None
        ):
            raise ValueError("Only running checkpoints may retain a worker.")

        if self.status is not DocumentBatchStatus.FAILED and (
            self.failure_message is not None
        ):
            raise ValueError("Only failed checkpoints may retain a failure.")

        return self
