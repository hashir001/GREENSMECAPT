"""Deterministic extraction of renewable-energy percentages."""

import re
from hashlib import sha256

from greensmecapt.document_intelligence.models import ExtractedDocument
from greensmecapt.domain import EvidenceItem, SourceDocument

_RENEWABLE_ENERGY_PATTERN = re.compile(
    r"\brenewable\s+energy"
    r"(?:\s+(?:use|usage|contribution|share))?"
    r"\s*(?::|=|\bis\b)?\s*"
    r"(?P<raw_value>"
    r"(?P<number>\d{1,3}(?:\.\d+)?)"
    r"\s*(?:%|percent\b)"
    r")",
    flags=re.IGNORECASE,
)


class RenewableEnergyPercentageExtractor:
    """Extract renewable-energy percentages from readable text."""

    extractor_name = "renewable_energy_percentage_regex"
    extractor_version = "1.0.0"

    def extract(
        self,
        document: SourceDocument,
        extracted_document: ExtractedDocument,
    ) -> tuple[EvidenceItem, ...]:
        """Return every valid renewable-energy percentage found."""

        evidence_items: list[EvidenceItem] = []

        for page in extracted_document.pages:
            for match in _RENEWABLE_ENERGY_PATTERN.finditer(page.text):
                normalized_value = float(match.group("number"))

                if not 0.0 <= normalized_value <= 100.0:
                    continue

                evidence_fingerprint = sha256(
                    (
                        f"{document.document_id}:"
                        f"{page.page_number}:"
                        f"{match.start()}:"
                        f"{match.end()}"
                    ).encode("utf-8")
                ).hexdigest()[:16]

                evidence_items.append(
                    EvidenceItem(
                        evidence_id=f"evidence_{evidence_fingerprint}",
                        sme_id=document.sme_id,
                        document_id=document.document_id,
                        indicator_id="renewable_energy_percentage",
                        criterion_id="renewable_energy",
                        raw_value=match.group("raw_value"),
                        normalized_value=normalized_value,
                        unit="percent",
                        source_locator=(
                            f"page {page.page_number}, "
                            f"characters {match.start()}-{match.end()}"
                        ),
                        source_excerpt=match.group(0),
                        extraction_method="regular_expression",
                        extractor_name=self.extractor_name,
                        extractor_version=self.extractor_version,
                        confidence=None,
                    )
                )

        return tuple(evidence_items)