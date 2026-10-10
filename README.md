# Inventory AI

Minimal hybrid SQL + RAG assistant for inventory questions.

The app routes a natural language question to SQL, RAG, or HYBRID processing, then returns a user-facing answer with optional SQL result data and document sources.

## What It Includes

* Streamlit web UI in `app/web/simple_server.py`
* CLI entry point in `main.py`
* SQL generation, validation, guardrails, and PostgreSQL execution
* RAG ingestion and retrieval with OpenAI embeddings and Qdrant
* PDF/TXT upload from the web UI for knowledge base updates
* Tests for routing, SQL safety, ingestion, parsing, chunking, and RAG

## Project Layout

* `app/orchestration/` - main question handling flow
* `app/services/` - routing, SQL generation, LLM answers, schema loading
* `app/security/` - prompt injection checks, SQL validator, limits
* `app/db/` - PostgreSQL connection and query execution
* `app/rag/` - parsing, chunking, embeddings, Qdrant retrieval
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

## Notes

Use `scripts/extract_schema.py` after database schema changes to refresh `config/schema.json`.
