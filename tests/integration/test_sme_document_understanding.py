"""Integration tests for multi-document SME understanding."""

from hashlib import sha256
from pathlib import Path

import pytest

from greensmecapt.document_intelligence.models import (
    ExtractedDocument,
    ExtractedPage,
    TextSource,
)
from greensmecapt.document_intelligence.reconciliation import (
    ReconciliationStatus,
)
from greensmecapt.document_intelligence.semantics import (
    SemanticMetricExtractor,
    load_metric_catalog,
)
from greensmecapt.document_intelligence.service import (
    DocumentIntegrityError,
)
from greensmecapt.document_intelligence.understanding import (
    DocumentSubmission,
    HybridSemanticExtractor,
    SMEDocumentUnderstandingService,
)
from greensmecapt.domain import SME, SourceDocument

CATALOG = load_metric_catalog(
    Path("config/metric_catalog.development.json")
)


class TextReader:
    """Convert UTF-8 content into one extracted page."""

    def read(
        self,
        document,
        content,
    ) -> ExtractedDocument:
        return ExtractedDocument(
            document_id=document.document_id,
            pages=(
                ExtractedPage(
                    page_number=1,
                    text=content.decode("utf-8"),
                    text_source=TextSource.PLAIN_TEXT,
                ),
            ),
        )


def _sme() -> SME:
    return SME(
        sme_id="sme_001",
        legal_name="EcoPack Manufacturing LLC",
        sector="Sustainable Packaging",
        jurisdiction="United Arab Emirates",
    )


def _submission(
    document_id: str,
    text: str,
) -> DocumentSubmission:
    content = text.encode()

    document = SourceDocument(
        document_id=document_id,
        sme_id="sme_001",
        file_name=f"{document_id}.txt",
        mime_type="text/plain",
        sha256=sha256(content).hexdigest(),
    )

    return DocumentSubmission(
        document=document,
        content=content,
    )


def _service() -> SMEDocumentUnderstandingService:
    return SMEDocumentUnderstandingService(
        reader=TextReader(),
        semantic_extractor=HybridSemanticExtractor(
            deterministic_extractor=(
                SemanticMetricExtractor(CATALOG)
            ),
            catalog=CATALOG,
        ),
    )


def test_build_reconciled_record_from_multiple_documents() -> None:
    """Equivalent facts from two documents should corroborate."""

    result = _service().process(
        sme=_sme(),
        submissions=(
            _submission(
                "doc_001",
                "Renewable energy share was 72 percent.",
            ),
            _submission(
                "doc_002",
                "72 percent of energy came from "
                "renewable sources.",
            ),
        ),
    )

    assert len(result.record.documents) == 2
    assert len(result.record.evidence_items) == 2
    assert result.reconciliation is not None
    assert len(result.reconciliation.clusters) == 1

    cluster = result.reconciliation.clusters[0]

    assert (
        cluster.status
        is ReconciliationStatus.CORROBORATED
    )
    assert cluster.candidate_values == (72.0,)
    assert cluster.document_ids == (
        "doc_001",
        "doc_002",
    )


def test_build_record_when_documents_contain_no_metrics() -> None:
    """A readable document need not fabricate evidence."""

    result = _service().process(
        sme=_sme(),
        submissions=(
            _submission(
                "doc_001",
                "The company opened a new facility.",
            ),
        ),
    )

    assert len(result.record.documents) == 1
    assert result.record.evidence_items == ()
    assert result.reconciliation is None


def test_reject_tampered_submission_content() -> None:
    """Registered hashes must still protect the full pipeline."""

    submission = _submission(
        "doc_001",
        "Renewable energy share was 72 percent.",
    )

    tampered = DocumentSubmission(
        document=submission.document,
        content=b"Renewable energy share was 10 percent.",
    )

    with pytest.raises(DocumentIntegrityError):
        _service().process(
            sme=_sme(),
            submissions=(tampered,),
        )