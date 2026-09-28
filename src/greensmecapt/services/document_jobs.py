"""Execute durable document-processing jobs."""

import logging
from uuid import uuid4

from greensmecapt.domain import (
    DocumentJobStatus,
    DocumentProcessingJob,
)
from greensmecapt.persistence import (
    GreenSMERepository,
    PersistenceConflictError,
)
from greensmecapt.services.document_processing import (
    DocumentProcessingError,
    StoredDocumentProcessingService,
)

_LOGGER = logging.getLogger("uvicorn.error")


class DocumentProcessingJobService:
    """Claim, execute and finalize one persisted processing job."""

    def __init__(self, processor: StoredDocumentProcessingService) -> None:
        self._processor = processor

    def run(
        self,
        *,
        repository: GreenSMERepository,
        job_id: str,
    ) -> DocumentProcessingJob:
        """Run one queued or retryable failed job."""

        worker_id = f"worker_{uuid4().hex}"

        try:
            job = repository.start_document_processing_job(
                job_id=job_id,
                worker_id=worker_id,
            )
        except PersistenceConflictError:
            return repository.get_document_processing_job(job_id)

        if job.status is DocumentJobStatus.COMPLETED:
            return job

        try:
            self._processor.process_in_batches(
                repository=repository,
                document_id=job.document_id,
                actor_id=job.requested_by,
                job_id=job.job_id,
                worker_id=worker_id,
            )
        except DocumentProcessingError as error:
            _LOGGER.exception(
                "Document processing job %s failed [%s]: %s",
                job.job_id,
                error.code,
                error.message,
            )
            return repository.fail_document_processing_job(
                job_id=job.job_id,
                worker_id=worker_id,
                failure_code=error.code,
                failure_message=error.message,
            )
        except Exception:
            _LOGGER.exception(
                "Document processing job %s failed unexpectedly.",
                job.job_id,
            )
            return repository.fail_document_processing_job(
                job_id=job.job_id,
                worker_id=worker_id,
                failure_code="internal_job_error",
                failure_message=(
                    "Document processing failed unexpectedly."
                ),
            )

        return repository.complete_document_processing_job(
            job_id=job.job_id,
            worker_id=worker_id,
        )
