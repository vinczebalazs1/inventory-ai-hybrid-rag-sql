from typing import Dict, List

from app.rag.retrieval.retriever import retrieve_by_name, retrieve_semantic
from app.services.llm_service import ask_llm


def _confidence_from_score(score) -> float | None:
    if score is None:
        return None

    try:
        normalized = max(0.0, min(1.0, float(score)))
    except (TypeError, ValueError):
        return None

    return round(normalized * 100, 1)


def build_sources(chunks: List[Dict]) -> List[Dict]:
    sources = []
    seen = set()

    for chunk in chunks:
        source = chunk.get("source") or chunk.get("name") or "-"
        section = chunk.get("section", "-")
        name = chunk.get("name", "-")
        key = (source, section, name)

        if key in seen:
            continue
        seen.add(key)

        sources.append({
            "source": source,
            "section": section,
            "name": name,
            "doc_type": chunk.get("doc_type", "-"),
            "confidence": _confidence_from_score(chunk.get("score")),
            "text": (chunk.get("text") or "")[:240],
        })

    return sources


def build_context(chunks: List[Dict]) -> str:
    """
    Chunk lista átalakítása LLM számára olvasható kontextussá.
    """

    if not chunks:
        return "No relevant documentation found."

    parts = []

    for c in chunks:
        source = c.get("source", c.get("name", "-"))
        doc_type = c.get("doc_type", "device_txt")
        part = f"""
DEVICE: {c["name"]}
SOURCE: {source}
DOC_TYPE: {doc_type}
SECTION: {c["section"]}
CONTENT:
{c["text"]}
"""
        parts.append(part.strip())

    return "\n\n".join(parts)


def answer_rag_details(question: str) -> Dict:
    """
    Válaszadás kizárólag RAG alapján, SQL nélkül.
    """

    chunks = retrieve_semantic(question)
    context = build_context(chunks)

    prompt = f"""
You are a helpful IT assistant.

Answer the user's question using ONLY the provided documentation.

If the answer is not in the context, say you don't know.

--- CONTEXT ---
{context}

--- QUESTION ---
{question}

--- ANSWER ---
"""

    return {
        "answer": ask_llm(prompt).strip(),
        "sources": build_sources(chunks),
    }


def answer_rag(question: str) -> str:
    return answer_rag_details(question)["answer"]


def answer_hybrid_details(question: str, names: List[str], sql_result: Dict) -> Dict:
    """
    Válaszadás SQL eredmény és RAG dokumentáció együttes használatával.
    """

    chunks = []
    normalized_names = []

    for name in names:
        if isinstance(name, str) and name.strip():
            normalized_names.append(name.strip().lower())

    for name in sorted(set(normalized_names)):
        chunks.extend(retrieve_by_name(name, question))

    if not chunks:
        chunks = retrieve_semantic(question)

    context = build_context(chunks)

    prompt = f"""
You are a smart assistant.

You have access to:
1. DATABASE RESULTS (structured data)
2. DEVICE DOCUMENTATION (usage, explanation)

Combine BOTH to answer the question clearly.

--- SQL RESULT ---
{sql_result}

--- DOCUMENTATION ---
{context}

--- QUESTION ---
{question}

--- ANSWER ---
"""

    return {
        "answer": ask_llm(prompt).strip(),
        "sources": build_sources(chunks),
    }


def answer_hybrid(question: str, names: List[str], sql_result: Dict) -> str:
    return answer_hybrid_details(question, names, sql_result)["answer"]
