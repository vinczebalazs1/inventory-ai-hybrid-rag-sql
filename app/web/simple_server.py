import streamlit as st
from app.orchestration.orchestrator import handle_question
from app.rag.ingestion.ingestion_service import ingest_uploaded_document

# Ezt a fájlt a Streamlit minden UI frissítéskor fentről lefelé végrehajtja.
# Szándékosan vékony marad: bekéri a felhasználói inputot, meghívja az orchestrator-t,
# majd kirendereli a visszakapott response dictet.
# python -m streamlit run app/web/simple_server.py
# Van a KGK-n telephelyen Laptop ami 2024 évi gyártású?
st.set_page_config(
    page_title="Inventory AI",
    page_icon="📦",
    layout="wide"
)

st.title("📦 Inventory AI")
st.caption("SQL + RAG + HYBRID assistant for inventory questions")

with st.sidebar:
    st.header("Controls")
    # A hibakeresés alapból ki van kapcsolva, hogy a normál felhasználó először
    # barátságos üzeneteket lásson. Bekapcsolva látszanak a technikai részletek.
    show_debug = st.toggle("Show debug", value=False)
    st.divider()
    st.markdown("**Knowledge base upload**")
    uploaded_docs = st.file_uploader(
        "Upload PDF or TXT",
        type=["pdf", "txt"],
        accept_multiple_files=True,
        help="Uploaded files are chunked, embedded, and stored in Qdrant for RAG answers."
    )
    ingest_uploads = st.button(
        "Add to knowledge base",
        use_container_width=True,
        disabled=not uploaded_docs
    )

    if ingest_uploads and uploaded_docs:
        with st.spinner("Indexing uploaded document..."):
            try:
                total_chunks = 0
                for uploaded_doc in uploaded_docs:
                    total_chunks += ingest_uploaded_document(
                        uploaded_doc.name,
                        uploaded_doc.getvalue()
                    )

                st.success(f"Uploaded and indexed {len(uploaded_docs)} file(s), {total_chunks} chunk(s).")
            except Exception as exc:
                st.error("The uploaded document could not be added to the knowledge base.")
                if show_debug:
                    st.exception(exc)

    st.divider()
    st.markdown("**Examples**")
    examples = [
      "Where is item E0001 located?",
      "Is the Laptop available in location KGK?",
      "Which items are stored in location GFB?"
    ]
    selected = st.radio("Try one:", examples, label_visibility="collapsed")

col1, col2 = st.columns([2, 1])

with col1:
    question = st.text_area(
        "Ask a question",
        value=selected,
        height=120,
        placeholder="Ask about products, stock, sales, suppliers..."
    )

with col2:
    st.metric("Mode", "HYBRID")
    st.info("Ask natural language questions. The system decides SQL, RAG, or hybrid routing.")

ask = st.button("🚀 Run analysis", type="primary", use_container_width=True)

if ask and question.strip():
    with st.spinner("Thinking..."):
        # Minden üzleti logika innen indul. A UI nem dönt SQL/RAG/HYBRID között;
        # ezt a döntést a handle_question() függvényre bízza.
        result = handle_question(question.strip())

    if not result.get("ok", True):
        error = result.get("error", {})

        # A handle_question() a backend exceptionöket biztonságos hibastruktúrává
        # alakítja, így a Streamlit nem mutat nagy piros tracebacket a felhasználónak.
        st.divider()
        st.warning(f"**{error.get('title', 'Valami figyelmet igényel')}**\n\n{error.get('message', 'Kérlek próbáld újra.')}")

        if show_debug and error.get("detail"):
            with st.expander("Technical details"):
                st.code(error["detail"])

        st.stop()

    route = result.get("route", "-")
    answer = result.get("answer", "-")
    sql = result.get("sql", "-")
    raw = result.get("result", {})
    sources = result.get("sources", [])

    st.divider()

    # Ezek a metrikák rövid futási összefoglalót adnak a kiválasztott feldolgozási láncról.
    c1, c2, c3 = st.columns(3)
    c1.metric("Route", route)
    c2.metric("SQL generated", "Yes" if sql and sql != "-" else "No")
    c3.metric("Result rows", raw.get("row_count", "-") if isinstance(raw, dict) else "-")

    st.subheader("Answer")
    st.success(answer)

    if sources:
        st.subheader("Sources")
        source_rows = []
        for idx, source in enumerate(sources, start=1):
            confidence = source.get("confidence")
            source_rows.append({
                "Citation": f"[{idx}] {source.get('source', '-')}",
                "Section": source.get("section", "-"),
                "Confidence": f"{confidence}%" if confidence is not None else "-",
                "Preview": source.get("text", ""),
            })

        st.dataframe(source_rows, use_container_width=True, hide_index=True)

    if show_debug:
        # A hibakeresési tabok belső feldolgozási adatokat mutatnak. Fejlesztés közben
        # hasznosak, de opcionálisak maradnak, mert a felhasználókat könnyen összezavarják.
        tab1, tab2 = st.tabs(["SQL", "Raw result"])

        with tab1:
            st.code(sql, language="sql")

        with tab2:
            st.json(raw)
