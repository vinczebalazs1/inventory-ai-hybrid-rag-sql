from typing import List, Dict
from app.rag.retrieval.retriever import retrieve_semantic, retrieve_by_name
from app.services.llm_service import ask_llm


def build_context(chunks: List[Dict]) -> str:
    """
    Convert chunk list into readable context for LLM.
    """

    if not chunks:
        return "No relevant documentation found."

    parts = []

    for c in chunks:
        part = f"""
DEVICE: {c["name"]}
SECTION: {c["section"]}
CONTENT:
{c["text"]}
"""
        parts.append(part.strip())

    return "\n\n".join(parts)


# 🟢 PURE RAG
def answer_rag(question: str) -> str:
    """
    Answer using only RAG (no SQL).
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

    return ask_llm(prompt).strip()


# 🔵 HYBRID
def answer_hybrid(question: str, names: List[str], sql_result: Dict) -> str:
    """
    Answer using both SQL result and RAG documentation.
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

    return ask_llm(prompt).strip()
