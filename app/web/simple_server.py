import streamlit as st
from app.orchestration.orchestrator import handle_question
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
    show_debug = st.toggle("Show debug", value=False)
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
        result = handle_question(question.strip())

    if not result.get("ok", True):
        error = result.get("error", {})

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

    st.divider()

    c1, c2, c3 = st.columns(3)
    c1.metric("Route", route)
    c2.metric("SQL generated", "Yes" if sql and sql != "-" else "No")
    c3.metric("Result rows", raw.get("row_count", "-") if isinstance(raw, dict) else "-")

    st.subheader("Answer")
    st.success(answer)

    if show_debug:
        tab1, tab2 = st.tabs(["SQL", "Raw result"])

        with tab1:
            st.code(sql, language="sql")

        with tab2:
            st.json(raw)
