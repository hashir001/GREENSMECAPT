"""Domain model for a document submitted as assessment evidence."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DocumentType(StrEnum):
    """Describe supported categories of SME documents."""

    UNKNOWN = "unknown"
    CONTRACT = "contract"
    FINANCIAL_STATEMENT = "financial_statement"
    PERMIT = "permit"
    UTILITY_BILL = "utility_bill"
    SUSTAINABILITY_REPORT = "sustainability_report"
    FUNDING_REQUEST = "funding_request"
    OTHER = "other"


class SourceDocument(BaseModel):
    """Represent one original document associated with an SME."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    document_id: str = Field(min_length=1)
    sme_id: str = Field(min_length=1)
    file_name: str = Field(min_length=1, pattern=r"^[^/\\]+$")
    mime_type: str = Field(min_length=1)
    sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    document_type: DocumentType = DocumentType.UNKNOWN