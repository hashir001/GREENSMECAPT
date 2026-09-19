"""Execute durable document-processing jobs."""

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

        try:
            job = repository.start_document_processing_job(job_id=job_id)
        except PersistenceConflictError:
            return repository.get_document_processing_job(job_id)

        if job.status is DocumentJobStatus.COMPLETED:
            return job

        try:
            self._processor.process(
                repository=repository,
                document_id=job.document_id,
                actor_id=job.requested_by,
            )
        except DocumentProcessingError as error:
            return repository.fail_document_processing_job(
                job_id=job.job_id,
                failure_code=error.code,
                failure_message=error.message,
            )
        except Exception:
            return repository.fail_document_processing_job(
                job_id=job.job_id,
                failure_code="internal_job_error",
                failure_message=(
                    "Document processing failed unexpectedly."
                ),
            )

        return repository.complete_document_processing_job(
            job_id=job.job_id
        )
