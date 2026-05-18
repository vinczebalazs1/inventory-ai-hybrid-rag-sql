from app.services.llm_service import ask_llm


def route_query(question: str) -> str:
    """
    Eldönti, hogy a kérdést melyik ág kezelje:
    - SQL
    - RAG
    - HYBRID
    """
    # A routing önmagában is LLM feladat. A prompt egyetlen szavas választ kér,
    # az alábbi parsing pedig ezt a három feldolgozási ág egyikére képezi le.
    prompt = f"""
You are a query classifier.

Classify the user question into ONE of these categories:

- SQL: questions about data (location, count, value, inventory)
- RAG: questions about usage, explanation, how something works
- HYBRID: combination of both

Return ONLY one word: SQL, RAG, or HYBRID.

--- EXAMPLES ---

Q: Where is the printer?
A: SQL

Q: How does a printer work?
A: RAG

Q: Where is the printer and how to use it?
A: HYBRID

--- QUESTION ---
{question}

--- ANSWER ---
"""
    response = ask_llm(prompt).strip().upper()

    # A sorrend számít: a "HYBRID" egyszerre jelent adat- és dokumentációs szándékot,
    # ezért előbb kell vizsgálni, mint a sima SQL-t.
    if "HYBRID" in response:
        return "HYBRID"
    if "SQL" in response:
        return "SQL"
    return "RAG"
