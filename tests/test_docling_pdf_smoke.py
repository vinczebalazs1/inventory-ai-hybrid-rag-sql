"""Explicit integration test because PDF layout/OCR models need a local cache."""
from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from app.document_processing.docling_parser import parse_document


def test_real_pdf(request):
    if not request.config.getoption("--run-docling-pdf"):
        pytest.skip("Enable --run-docling-pdf to download/use the PDF models")
    writer = PdfWriter()
    page = writer.add_blank_page(width=595, height=842)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                             NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 50 780 Td (Inventory No.: INV-123) Tj 0 -20 Td (Location: Budapest) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    buffer = BytesIO()
    writer.write(buffer)
    result = parse_document(buffer.getvalue(), "demo.pdf")
    assert "INV-123" in result.markdown
    assert "Budapest" in result.pages[1]
    assert "[PAGE 1]" in result.extraction_text
