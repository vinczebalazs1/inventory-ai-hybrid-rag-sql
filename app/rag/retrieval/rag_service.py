from typing import Dict, List

from app.rag.retrieval.retriever import retrieve_by_model, retrieve_semantic
from app.rag.embedding.embedding_service import embed_text
from app.rag.manuals import load_manifest, model_status, sql_model_pairs, MANUAL_TYPE
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
            "item_code": chunk.get("item_code"),
            "source_url": chunk.get("source_url"),
            "source_sha256": chunk.get("source_sha256"),
            "page": chunk.get("page"),
            "source_kind": "manufacturer" if chunk.get("doc_type") == MANUAL_TYPE else "general",
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
SCOPE: {"Manufacturer documentation for this exact model" if doc_type == MANUAL_TYPE else "General documentation, not proof for a specific model"}
ITEM_CODE: {c.get("item_code", "-")}
URL: {c.get("source_url", "-")}
PDF_PAGE: {c.get("page", "-")}
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
Distinguish general advice from manufacturer information. Respect the stated model
scope of each source. Cite source and PDF page when using a manufacturer manual.

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

    # `names` remains for the public call contract; SQL rows are authoritative.
    pairs = sql_model_pairs(sql_result)
    documents = load_manifest()
    chunks, statuses = [], []
    vector = None
    for name, code in pairs:
        status = model_status(name, code, documents)
        if status == "documented":
            if vector is None:
                vector = embed_text(question)
            found = retrieve_by_model(name, code, question, vector=vector)
            chunks.extend(found)
            status = "matched" if found else "not_indexed"
        statuses.append({"name": name, "item_code": code, "status": status})
    if not pairs:
        statuses.append({"name": None, "item_code": None, "status": "missing_model_identity"})

    messages = {
        "undocumented_model": "Nincs ehhez a modellhez ellenőrzött, betöltött gyártói dokumentáció.",
        "identifier_conflict": "A név–cikkszám kombináció nem egyezik a dokumentumjegyzékkel; dokumentum nem kapcsolható hozzá.",
        "not_indexed": "A modell kézikönyve szerepel a jegyzékben, de nincs megfelelő indexelt részlet.",
        "missing_model_identity": "Az SQL-eredmény nem tartalmaz egyértelmű name és item_code modellazonosítót; gyártói dokumentáció nem kapcsolható hozzá.",
    }
    notices = [f"{s['name'] or 'Modell'} ({s['item_code'] or '-'}): {messages[s['status']]}"
               for s in statuses if s["status"] != "matched"]
    if not chunks:
        # Deterministic abstention: no LLM can invent unsupported technical advice.
        columns = sql_result.get("columns", [])
        facts = ["; ".join(f"{c}: {v}" for c, v in zip(columns, row))
                 for row in sql_result.get("rows", [])[:10]]
        answer = "\n".join(notices + (["SQL-találatok:"] + facts if facts else []))
        return {"answer": answer, "sources": [], "documentation_status": statuses}

    context = build_context(chunks)

    prompt = f"""
You are a smart assistant.

You have access to:
1. DATABASE RESULTS (structured data)
2. DEVICE DOCUMENTATION (usage, explanation)

Combine BOTH to answer the question clearly.
Use only the supplied SQL facts and documentation. Each manual applies ONLY to
its exact DEVICE and ITEM_CODE pair. Never transfer advice to a different model.
Do not invent instructions missing from these reviewed excerpts. Retain safety
conditions in procedures. Cite the source and PDF page for technical statements.
For models without matched documentation, state that documentation is unavailable.

--- DOCUMENTATION COVERAGE ---
{statuses}

--- SQL RESULT ---
{sql_result}

--- DOCUMENTATION ---
{context}

--- QUESTION ---
{question}

--- ANSWER ---
"""

    return {
        "answer": "\n".join(notices + [ask_llm(prompt).strip()]),
        "sources": build_sources(chunks),
        "documentation_status": statuses,
    }


def answer_hybrid(question: str, names: List[str], sql_result: Dict) -> str:
    return answer_hybrid_details(question, names, sql_result)["answer"]
