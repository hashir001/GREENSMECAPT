"""Integration test for native PDF layout and table extraction."""

from hashlib import sha256
from io import BytesIO

from pypdf import PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)

from greensmecapt.document_intelligence.readers.pdf import (
    PdfTextDocumentReader,
)
from greensmecapt.domain import SourceDocument


def _make_table_pdf() -> bytes:
    """Create a small native PDF containing a ruled data table."""

    writer = PdfWriter()
    page = writer.add_blank_page(
        width=612,
        height=792,
    )

    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject(
                "/Helvetica"
            ),
        }
    )

    resources = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {
                    NameObject("/F1"): writer._add_object(
                        font
                    ),
                }
            ),
        }
    )

    page[NameObject("/Resources")] = resources

    commands = b"""
0.5 w
50 650 m 450 650 l S
50 680 m 450 680 l S
50 710 m 450 710 l S
50 740 m 450 740 l S
50 650 m 50 740 l S
250 650 m 250 740 l S
350 650 m 350 740 l S
450 650 m 450 740 l S

BT /F1 10 Tf 60 720 Td (Metric) Tj ET
BT /F1 10 Tf 270 720 Td (2024) Tj ET
BT /F1 10 Tf 370 720 Td (Unit) Tj ET

BT /F1 10 Tf 60 690 Td (Renewable electricity) Tj ET
BT /F1 10 Tf 270 690 Td (68) Tj ET
BT /F1 10 Tf 370 690 Td (%) Tj ET

BT /F1 10 Tf 60 660 Td (Scope 1 emissions) Tj ET
BT /F1 10 Tf 270 660 Td (151) Tj ET
BT /F1 10 Tf 370 660 Td (tCO2e) Tj ET
"""

    stream = DecodedStreamObject()
    stream.set_data(commands)

    page[NameObject("/Contents")] = writer._add_object(
        stream
    )

    output = BytesIO()
    writer.write(output)

    return output.getvalue()


def test_read_native_pdf_layout_and_table() -> None:
    """A native PDF table should retain rows, columns and values."""

    content = _make_table_pdf()

    document = SourceDocument(
        document_id="doc_table_001",
        sme_id="sme_001",
        file_name="environmental_performance.pdf",
        mime_type="application/pdf",
        sha256=sha256(content).hexdigest(),
    )

    extracted = PdfTextDocumentReader().read(
        document=document,
        content=content,
    )

    assert len(extracted.pages) == 1

    page = extracted.pages[0]

    assert page.page_width == 612
    assert page.page_height == 792
    assert len(page.tables) == 1

    table = page.tables[0]
    matrix = table.as_matrix()

    assert matrix[0] == ("Metric", "2024", "Unit")
    assert matrix[1] == (
        "Renewable electricity",
        "68",
        "%",
    )
    assert matrix[2] == (
        "Scope 1 emissions",
        "151",
        "tCO2e",
    )
    assert table.value_at(1, 1) == "68"
    assert table.header_row_indices == (0,)