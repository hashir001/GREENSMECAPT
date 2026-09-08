"""Integration test for plain-text evidence extraction."""

from hashlib import sha256

from greensmecapt.document_intelligence import (
    DocumentIntelligenceService,
    PlainTextDocumentReader,
    RenewableEnergyPercentageExtractor,
)
from greensmecapt.domain import (
    SME,
    DocumentType,
    SourceDocument,
    StructuredInvestmentRecord,
)

DOCUMENT_CONTENT = b"Renewable energy contribution: 72%"


def test_plain_text_document_becomes_investment_record() -> None:
    """A real text document should produce a structured SME record."""

    sme = SME(
        sme_id="sme_001",
        legal_name="EcoPack Manufacturing LLC",
        sector="Sustainable Packaging",
        jurisdiction="United Arab Emirates",
    )

    document = SourceDocument(
        document_id="doc_001",
        sme_id=sme.sme_id,
        file_name="sustainability_statement.txt",
        mime_type="text/plain",
        sha256=sha256(DOCUMENT_CONTENT).hexdigest(),
        document_type=DocumentType.SUSTAINABILITY_REPORT,
    )

    service = DocumentIntelligenceService(
        reader=PlainTextDocumentReader(),
        evidence_extractor=RenewableEnergyPercentageExtractor(),
    )

    evidence_items = service.process(
        document=document,
        content=DOCUMENT_CONTENT,
    )

    record = StructuredInvestmentRecord(
        sme=sme,
        documents=(document,),
        evidence_items=evidence_items,
    )

    assert len(record.evidence_items) == 1
    assert record.evidence_items[0].normalized_value == 72.0
    assert record.evidence_items[0].sme_id == sme.sme_id