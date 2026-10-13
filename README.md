# Inventory AI

Minimal hybrid SQL + RAG assistant for inventory questions.

The app routes a natural language question to SQL, RAG, or HYBRID processing, then returns a user-facing answer with optional SQL result data and document sources.

## What It Includes

* Streamlit web UI in `app/web/simple_server.py`
* CLI entry point in `main.py`
* SQL generation, validation, guardrails, and PostgreSQL execution
* RAG ingestion and retrieval with OpenAI embeddings and Qdrant
* PDF/TXT upload from the web UI for knowledge base updates
* PDF/DOCX analysis with Docling, field extraction and inventory schema mapping
* Read-only PostgreSQL record reconciliation, field differences and review suggestions
* Tests for routing, SQL safety, ingestion, parsing, chunking, and RAG

## Project Layout

* `app/orchestration/` - main question handling flow
* `app/services/` - routing, SQL generation, LLM answers, schema loading
* `app/security/` - prompt injection checks, SQL validator, limits
* `app/db/` - PostgreSQL connection and query execution
* `app/rag/` - parsing, chunking, embeddings, Qdrant retrieval
* `app/document_processing/` - Docling parsing, extraction, mapping and validation
* `app/record_matching/` - candidate search, deterministic ranking, comparisons and suggestions
* `app/evaluation/` - offline matching evaluation and metrics
* `app/web/` - Streamlit UI
* `config/` - schema and column mapping files
* `scripts/` - helper scripts
* `tests/` - automated tests

## Setup

Create and activate a virtual environment, then install dependencies:

`python -m venv venv`

`venv\Scripts\activate`

`pip install -r requirements.txt`

Create `.env` from `.env.example` and fill in the required values.

Required configuration:

* `OPENAI_API_KEY`
* `DB_NAME`
* `DB_USER`
* `DB_PASSWORD`
* `DB_HOST`
* `DB_PORT`

RAG also expects Qdrant configuration:

* `QDRANT_URL`
* `QDRANT_API_KEY`
* `QDRANT_COLLECTION` optional, defaults to `devices`

## Run

Web UI:

`python -m streamlit run app/web/simple_server.py`

CLI:

`python main.py`

## Tests

`pytest`

## Document analysis (Docling)

The **Dokumentum elemzése – PDF / DOCX** panel provides generic field extraction,
inventory schema mapping, validation and an evidence-based preview without database
writes. The existing RAG upload remains separate.

Install development dependencies with `pip install -r requirements-dev.txt`.
Prepare PDF models with `python -m scripts.prepare_docling_models` (internet required).
See [Document processing V1](docs/document_processing_v1.md) for setup, configuration,
data models, usage and limitations.

## Rekordegyeztetés és javaslatok

Az elemzett PDF/DOCX adatai a **Dokumentum elemzése – PDF / DOCX** panel
**Egyeztetés az adatbázissal** gombjával hasonlíthatók össze a PostgreSQL leltárral.
Az egyeztetés a már elkészült elemzést használja; nem indít új LLM-hívást.

1. Tölts fel dokumentumot és indítsd el az **Analyze document** elemzést.
2. Ellenőrizd a kinyert mezőket és a dokumentumbeli bizonyítékokat.
3. Kattints az **Egyeztetés az adatbázissal** gombra.
4. Nézd át a rangsorolt találatokat, az eltérő mezőket és a javasolt műveleteket.

A működéshez a meglévő `DB_*` konfiguráció és a táblát, illetve annak sémáját
olvasni képes PostgreSQL-hozzáférés kell. A modul ellenőrzi a tényleges oszlopokat
és egyediségi feltételeket. Ha nem igazolható stabil rekordazonosító, azt jelzi;
egyező eszköznévből nem következtet garantált rekordazonosságra.

A `MATCHING_*` beállítások mintái a `.env.example` fájlban találhatók. Az eredmény
munkamenetben marad: új feltöltés és újraelemzés törli. A javaslatok nem hajtanak
végre adatbázisfrissítést, új rekord létrehozását vagy dokumentumcsatolást.

Részletes használat, algoritmus, konfiguráció és korlátok:
[Rekordegyeztetés](docs/record_reconciliation.md).

Az offline mérés élő LLM és adatbázis nélkül futtatható. A reprodukálható
parancsokat, a metrikák definícióit és a szintetikus adatok korlátait a
[kiértékelési útmutató](docs/record_matching_evaluation.md) tartalmazza.

```powershell
venv\Scripts\python -m scripts.evaluate_matching --repeats 5
venv\Scripts\python -m pytest -q --run-docling-pdf --run-matching-postgres
```

A PostgreSQL-integrációs teszt saját, ideiglenes helyi klasztert indít; az üzleti
adatbázist nem használja. A binárisok helye `MATCHING_TEST_PG_BIN` változóval adható meg.
A teljes megvalósítási és elfogadási riport: [ellenőrzési riport](docs/record_reconciliation_report.md).

## Notes

Use `scripts/extract_schema.py` after database schema changes to refresh `config/schema.json`.
