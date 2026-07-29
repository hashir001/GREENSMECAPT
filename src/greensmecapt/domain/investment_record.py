"""Structured investment record assembled from SME evidence."""

from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from greensmecapt.domain.evidence import EvidenceItem
from greensmecapt.domain.sme import SME
from greensmecapt.domain.source_document import SourceDocument


class StructuredInvestmentRecord(BaseModel):
    """Group one SME with its source documents and extracted evidence."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    sme: SME
    documents: tuple[SourceDocument, ...] = ()
    evidence_items: tuple[EvidenceItem, ...] = ()

    @model_validator(mode="after")
    def validate_record_relationships(self) -> Self:
        """Ensure every record component belongs together correctly."""

        document_ids = [
            document.document_id for document in self.documents
        ]
        evidence_ids = [
            evidence.evidence_id for evidence in self.evidence_items
        ]

        if len(document_ids) != len(set(document_ids)):
            raise ValueError("Document IDs must be unique within a record.")

        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("Evidence IDs must be unique within a record.")

        document_id_set = set(document_ids)

        for document in self.documents:
            if document.sme_id != self.sme.sme_id:
                raise ValueError(
                    "Every document must belong to the record's SME."
                )

        for evidence in self.evidence_items:
            if evidence.sme_id != self.sme.sme_id:
                raise ValueError(
                    "Every evidence item must belong to the record's SME."
                )

            if evidence.document_id not in document_id_set:
                raise ValueError(
                    "Every evidence item must reference a record document."
                )

        return self