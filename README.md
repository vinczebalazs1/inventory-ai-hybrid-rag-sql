# Inventory AI – Hybrid RAG + SQL Query System

AI-powered system for querying inventory data and technical documentation using natural language.

## 🧠 Overview

Inventory AI is a hybrid LLM-based system designed to bridge the gap between structured database queries and unstructured document retrieval.

The system allows users to ask natural language questions and automatically decides how to answer them using:

* SQL queries (structured data)
* RAG (document-based knowledge)
* Hybrid processing (combination of both)

## 🎯 Problem

Traditional systems separate:

* database queries (SQL)
* document search (manual lookup)

This project combines both into a unified intelligent interface.

## 🏗️ Architecture

The system follows a modular architecture:

* **Backend API (Python / FastAPI)**
* **Query Router (LLM-based decision)**
* **SQL Engine (Text-to-SQL + execution)**
* **RAG Engine (vector search + LLM)**
* **Answer Generator (final response synthesis)**

👉 The architecture processes user input from question → routing → execution → final answer.

## 🔄 Query Types

The system supports 3 query types:

### 1. SQL Queries

Example:

> "Where is the projector?"

* Converted to SQL
* Executed on PostgreSQL
* Returns structured result

### 2. RAG Queries

Example:

> "How to calibrate a 3D printer?"

* Vector search in documentation
* Relevant chunks retrieved
* LLM generates answer

### 3. Hybrid Queries

Example:

> "How many 3D printers are available and how to maintain them?"

* SQL → retrieves quantity
* RAG → retrieves documentation
* LLM → merges results into final answer

## ⚙️ Tech Stack

* **Python**
* **FastAPI**
* **OpenAI (GPT-4)**
* **PostgreSQL**
* **Vector DB (Qdrant)**
* **LLM-based routing & generation**

## 🔐 Security

* SQL query validation (SELECT only)
* Injection protection
* Guardrails for LLM output
* Query limits and timeouts

## 📂 Project Structure

```bash
app/
 ├── orchestration/     # pipeline, planner
 ├── services/          # LLM + SQL generation
 ├── security/          # validation & guardrails
 ├── prompts/           # prompt templates
 ├── db/                # DB connection & execution
 └── models/            # data schemas

config/
scripts/
tests/
main.py
```

## ⚙️ Setup

```bash
git clone https://github.com/vinczebalazs1/inventory-ai-hybrid-rag-sql.git
cd inventory-ai-hybrid-rag-sql

python -m venv venv
venv\Scripts\activate

pip install -r requirements.txt
```

## 🔐 Environment Variables

Create a `.env` file:

```bash
cp .env.example .env
```

Fill in your credentials (API keys, DB config).

## ▶️ Run

```bash
python main.py
```

## 🧪 Testing

```bash
pytest
```

## 💡 Key Features

* Natural language → SQL generation
* Semantic document retrieval (RAG)
* Intelligent query routing
* Hybrid answer synthesis
* Modular and extensible architecture

## 📈 Future Improvements

* Web UI
* API endpoints
* Logging & monitoring
* Deployment (Docker / Cloud)

## 👤 Author

Balázs Vincze
