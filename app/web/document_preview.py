"""Streamlit presentation for the independent document processing branch."""
import json

import streamlit as st

from app.document_processing.config import Settings
from app.document_processing.processing_service import process_document
from app.errors import AppError
from app.web.reconciliation_preview import clear_reconciliation, render_reconciliation


def _clear_preview() -> None:
    st.session_state.pop("document_preview", None)
    clear_reconciliation()


def render_document_analysis(show_debug: bool = False) -> None:
    st.header("Dokumentum elemzése")
    st.caption("PDF vagy DOCX → mezőkinyerés → leltári megfeleltetés → előnézet. Az adatok nem kerülnek mentésre.")
    uploaded = st.file_uploader("Elemzendő dokumentum", type=["pdf", "docx"],
                               key="analysis_upload", on_change=_clear_preview)
    if st.button("Analyze document", disabled=uploaded is None):
        _clear_preview()
        with st.spinner("Dokumentum feldolgozása…"):
            try:
                st.session_state["document_preview"] = process_document(uploaded.getvalue(), uploaded.name)
            except AppError as exc:
                st.error(str(exc))
                if show_debug:
                    st.exception(exc)
    result = st.session_state.get("document_preview")
    if result is None:
        return
    st.caption(f"Eredmény forrása: {result.parsed_document.source_name}")
    st.subheader("Document type")
    st.write(result.extraction.document_type or "Ismeretlen")
    for title, fields in (
        ("Mapped fields", result.mapping.mapped_fields),
        ("Unmapped fields", result.mapping.unmapped_fields),
        ("Validation issues", result.validation_issues),
    ):
        st.subheader(title)
        rows = [field.model_dump() for field in fields]
        if rows:
            for row in rows:
                if row.get("normalized_value") is not None:
                    row["normalized_value"] = str(row["normalized_value"])
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.caption("Nincs.")
    render_reconciliation(result, show_debug=show_debug)
    with st.expander("Debug / raw output"):
        st.code(result.parsed_document.extraction_text, language="markdown")
        st.json(result.extraction.model_dump(mode="json"))
        st.json(result.mapping.model_dump(mode="json"))
        if show_debug and result.parsed_document.raw_document is not None:
            raw = json.dumps(result.parsed_document.raw_document, ensure_ascii=False)
            if len(raw.encode("utf-8")) <= Settings().debug_json_bytes:
                st.json(raw)
            else:
                st.caption("A teljes Docling JSON túl nagy a megjelenítéshez.")
