from app.rag.ingestion.chunker import chunk_document_text
from app.rag.ingestion.document_parser import extract_text_from_upload


def test_extract_text_from_uploaded_txt():
    text, doc_type = extract_text_from_upload(
        "manual.txt",
        "Első sor\n\nMásodik sor".encode("utf-8"),
    )

    assert doc_type == "txt"
    assert "Első sor" in text
    assert "Második sor" in text


def test_chunk_document_text_adds_source_metadata():
    chunks = chunk_document_text(
        "Ez egy feltöltött dokumentum tartalma. " * 80,
        source="manual.pdf",
        doc_type="pdf",
        chunk_size=300,
        overlap=50,
    )

    assert len(chunks) > 1
    assert chunks[0].name == "manual.pdf"
    assert chunks[0].source == "manual.pdf"
    assert chunks[0].doc_type == "pdf"
    assert chunks[0].section == "chunk-1"
