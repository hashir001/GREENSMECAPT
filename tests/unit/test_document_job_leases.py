"""Tests for durable processing-job ownership and recovery."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest

from greensmecapt.domain import (
    SME,
    DocumentBatchCheckpoint,
    DocumentBatchStatus,
    DocumentJobStatus,
    SourceDocument,
    StructuredInvestmentRecord,
)
from greensmecapt.persistence import (
    Database,
    GreenSMERepository,
    PersistenceConflictError,
)


def _repository(tmp_path: Path):
    database = Database(
        f"sqlite:///{tmp_path / 'job-leases.db'}"
    )
    database.create_schema()
    return database


def _register_document(
    repository: GreenSMERepository,
) -> SourceDocument:
    sme = SME(
        sme_id="sme_001",
        legal_name="EcoPack Manufacturing LLC",
        sector="Sustainable Packaging",
        jurisdiction="United Arab Emirates",
    )
    repository.save_record(
        StructuredInvestmentRecord(sme=sme)
    )
    content = b"Renewable energy share: 72 percent."
    document = SourceDocument(
        document_id="doc_001",
        sme_id=sme.sme_id,
        file_name="report.txt",
        mime_type="text/plain",
        sha256=sha256(content).hexdigest(),
    )
    repository.attach_document(
        document=document,
        storage_key="sme_001/doc_001/content",
        actor_id="user_001",
    )
    return document


def test_active_worker_lease_blocks_second_worker(
    tmp_path: Path,
) -> None:
    """Two workers must not process the same job concurrently."""

    database = _repository(tmp_path)

    with database.session() as session:
        repository = GreenSMERepository(session)
        document = _register_document(repository)
        queued = repository.enqueue_document_processing(
            document_id=document.document_id,
            actor_id="user_001",
        )
        running = repository.start_document_processing_job(
            job_id=queued.job_id,
            worker_id="worker_a",
            lease_seconds=60,
        )

        with pytest.raises(PersistenceConflictError):
            repository.start_document_processing_job(
                job_id=queued.job_id,
                worker_id="worker_b",
                lease_seconds=60,
            )

    assert running.status is DocumentJobStatus.RUNNING
    assert running.worker_id == "worker_a"
    assert running.last_heartbeat_at is not None


def test_expired_worker_lease_becomes_retryable(
    tmp_path: Path,
) -> None:
    """Abandoned work should fail explicitly and resume under a new worker."""

    database = _repository(tmp_path)

    with database.session() as session:
        repository = GreenSMERepository(session)
        document = _register_document(repository)
        queued = repository.enqueue_document_processing(
            document_id=document.document_id,
            actor_id="user_001",
        )
        running = repository.start_document_processing_job(
            job_id=queued.job_id,
            worker_id="worker_a",
            lease_seconds=60,
        )
        recovered = repository.recover_stale_document_processing_jobs(
            as_of=running.lease_expires_at + timedelta(seconds=1)
        )
        restarted = repository.start_document_processing_job(
            job_id=queued.job_id,
            worker_id="worker_b",
            lease_seconds=60,
        )

    assert len(recovered) == 1
    assert recovered[0].status is DocumentJobStatus.FAILED
    assert recovered[0].failure_code == "worker_lease_expired"
    assert restarted.status is DocumentJobStatus.RUNNING
    assert restarted.worker_id == "worker_b"
    assert restarted.attempt_count == 2


def test_only_lease_owner_can_complete_job(
    tmp_path: Path,
) -> None:
    """A stale worker must not finalize another worker's result."""

    database = _repository(tmp_path)

    with database.session() as session:
        repository = GreenSMERepository(session)
        document = _register_document(repository)
        queued = repository.enqueue_document_processing(
            document_id=document.document_id,
            actor_id="user_001",
        )
        repository.start_document_processing_job(
            job_id=queued.job_id,
            worker_id="worker_a",
        )

        with pytest.raises(PersistenceConflictError):
            repository.complete_document_processing_job(
                job_id=queued.job_id,
                worker_id="worker_b",
            )


def test_completed_page_checkpoint_survives_later_batch_failure(
    tmp_path: Path,
) -> None:
    """Retrying one page batch must not discard completed batch output."""

    database = _repository(tmp_path)

    with database.session() as session:
        repository = GreenSMERepository(session)
        document = _register_document(repository)
        queued = repository.enqueue_document_processing(
            document_id=document.document_id,
            actor_id="user_001",
        )
        repository.start_document_processing_job(
            job_id=queued.job_id,
            worker_id="worker_a",
        )
        now = datetime.now(UTC)
        checkpoints = tuple(
            DocumentBatchCheckpoint(
                checkpoint_id=(
                    f"{queued.job_id}_checkpoint_{batch_number}"
                ),
                job_id=queued.job_id,
                document_id=document.document_id,
                batch_id=f"batch_{batch_number}",
                page_numbers=page_numbers,
                created_at=now,
                updated_at=now,
            )
            for batch_number, page_numbers in (
                (1, (1, 2)),
                (2, (3, 4)),
            )
        )
        planned = repository.initialize_document_batch_checkpoints(
            job_id=queued.job_id,
            checkpoints=checkpoints,
        )
        first = repository.start_document_batch_checkpoint(
            checkpoint_id=planned[0].checkpoint_id,
            worker_id="worker_a",
        )
        repository.complete_document_batch_checkpoint(
            checkpoint_id=first.checkpoint_id,
            worker_id="worker_a",
            result_json='{"pages": [1, 2]}',
        )
        second = repository.start_document_batch_checkpoint(
            checkpoint_id=planned[1].checkpoint_id,
            worker_id="worker_a",
        )
        repository.fail_document_batch_checkpoint(
            checkpoint_id=second.checkpoint_id,
            worker_id="worker_a",
            failure_message="OCR timed out on page 4.",
        )
        saved = repository.list_document_batch_checkpoints(
            queued.job_id
        )

    assert saved[0].status is DocumentBatchStatus.COMPLETED
    assert saved[0].result_json == '{"pages": [1, 2]}'
    assert saved[1].status is DocumentBatchStatus.FAILED
    assert saved[1].attempt_count == 1
