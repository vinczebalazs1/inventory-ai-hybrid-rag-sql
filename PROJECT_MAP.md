# Inventory AI Project Map

## Projekt celja

Az Inventory AI egy kerdes-valasz rendszer leltari adatokhoz es eszkoz dokumentaciohoz.

A user termeszetes nyelven kerdez, a rendszer pedig eldonti, hogy:

- SQL-lel kell valaszolni strukturalt adatbazisbol,
- RAG-gel kell valaszolni dokumentaciobol,
- vagy HYBRID modon mindkettot ossze kell kombinalni.

## Fo belepesi pont

Fo webes belepesi pont:

```text
app/web/simple_server.py
```

Ez egy Streamlit UI. Itt jelenik meg a szovegmezos input, a futtato gomb, majd itt jelenik meg a valasz, a route, az SQL es a nyers eredmeny is.

Masodlagos konzolos belepesi pont:

```text
main.py
```

Ez terminalbol ker be egy kerdest, meghivja ugyanazt a `handle_question()` fuggvenyt, majd kiirja a route-ot, SQL-t, strukturalt eredmenyt es vegso valaszt.

## Teljes kerdes-valasz flow

```text
User question
↓
Streamlit UI
↓
app/web/simple_server.py
↓
handle_question(question)
↓
app/orchestration/orchestrator.py
↓
Prompt injection check
↓
Router
↓
app/services/routing_service.py
↓
├─ SQL route
│  ↓
│  Text-to-SQL
│  ↓
│  SQL validation + LIMIT guardrail
│  ↓
│  PostgreSQL execution
│  ↓
│  Natural-language answer generation
│
├─ RAG route
│  ↓
│  Embed question
│  ↓
│  Qdrant semantic search
│  ↓
│  Build context
│  ↓
│  LLM answer from documentation
│
└─ HYBRID route
   ↓
   SQL pipeline
   ↓
   Extract item/device names from SQL result
   ↓
   RAG retrieval by name, fallback semantic search
   ↓
   LLM combines SQL result + documentation
↓
Final answer
↓
Streamlit UI display
```

## Honnan indul a user kerdes?

Fajl:

```text
app/web/simple_server.py
```

A kerdes itt indul:

```python
question = st.text_area(...)
ask = st.button(...)
```

Amikor a user megnyomja a gombot:

```python
if ask and question.strip():
    result = handle_question(question.strip())
```

Tehat a Streamlit UI nem maga dolgozza fel a kerdest. Csak osszegyujti az inputot, meghivja az orchestratort, majd megjeleniti a kapott `result` dictet.

## Orchestrator szerepe

Fajl:

```text
app/orchestration/orchestrator.py
```

Fo fuggveny:

```python
handle_question(question: str) -> dict
```

Ez a rendszer kozponti iranyitoja. A kerdes itt megy at biztonsagi ellenorzesen, route-dontesen, majd innen indul el az SQL, RAG vagy HYBRID ag.

## Router mukodese

Fajl:

```text
app/services/routing_service.py
```

Fo fuggveny:

```python
route_query(question: str) -> str
```

Ez LLM-et hiv, es a kerdest harom kategoriaba sorolja:

- `SQL`: adat, hely, darabszam, ertek, inventory jellegu kerdesek.
- `RAG`: hasznalat, magyarazat, hogyan mukodik jellegu kerdesek.
- `HYBRID`: egyszerre kell adatbazis es dokumentacio.

Ha a modell valaszaban nincs `HYBRID` vagy `SQL`, akkor fallbackkent `RAG` lesz.

## SQL ag mukodese

Az SQL ag akkor fut, ha a router `SQL` route-ot ad vissza.

Lepesek:

```text
generate_sql(question)
↓
validate_sql(raw_sql)
↓
ensure_limit(validated_sql)
↓
execute_query(safe_sql)
↓
generate_natural_answer(question, safe_sql, result)
```

Erintett fajlok:

- `app/services/sql_generation_service.py`: betolti a text-to-SQL promptot, hozzaadja a semat, majd LLM-mel SQL-t general.
- `app/services/schema_service.py`: a `config/schema.json` es `config/schema_descriptions.yaml` alapjan olvashato semaszoveget keszit az LLM-nek.
- `app/security/sql_validator.py`: ellenorzi, hogy csak `SELECT` vagy `WITH` query fusson, es tiltja a veszelyes SQL kulcsszavakat.
- `app/security/guardrails.py`: LIMIT-et tesz a queryre, vagy tul nagy LIMIT-et lejjebb vesz.
- `app/db/connection.py`: PostgreSQL kapcsolatot nyit `.env` alapjan.
- `app/db/executor.py`: lefuttatja a SQL-t, majd `columns`, `rows`, `row_count` strukturaban ad vissza eredmenyt.
- `app/services/answer_service.py`: a SQL eredmenybol magyar, rovid termeszetes nyelvu valaszt keszit.

SQL ag visszaterese:

```python
{
    "ok": True,
    "question": question,
    "route": "SQL",
    "sql": safe_sql,
    "result": result,
    "answer": answer,
    "matched_names": [],
}
```

## RAG ag mukodese

Az RAG ag akkor fut, ha a router `RAG` route-ot ad vissza.

Lepesek:

```text
answer_rag(question)
↓
retrieve_semantic(question)
↓
embed_text(question)
↓
Qdrant search
↓
build_context(chunks)
↓
ask_llm(prompt with context)
```

Erintett fajlok:

- `app/rag/retrieval/rag_service.py`: osszerakja a dokumentacios kontextust es meghivja az LLM-et.
- `app/rag/retrieval/retriever.py`: embeddinget keszit a kerdesbol, majd Qdrantban keres.
- `app/rag/embedding/embedding_service.py`: OpenAI embedding modellel vektorra alakitja a szoveget.
- `app/rag/vector_store/qdrant_client.py`: Qdrant kliens, collection es keresesi muveletek.

RAG ag visszaterese:

```python
{
    "ok": True,
    "question": question,
    "route": "RAG",
    "sql": None,
    "result": {"columns": [], "rows": [], "row_count": 0},
    "answer": answer,
    "matched_names": [],
}
```

## HYBRID ag mukodese

Az HYBRID ag akkor fut, ha a router `HYBRID` route-ot ad vissza.

Lepesek:

```text
SQL pipeline
↓
_extract_names_from_sql_result(result)
↓
answer_hybrid(question, matched_names, result)
↓
retrieve_by_name(name, question)
↓
fallback: retrieve_semantic(question), ha nincs nev szerinti talalat
↓
build_context(chunks)
↓
ask_llm(prompt with SQL result + documentation)
```

Itt eloszor strukturalt adatot keres az adatbazisban, majd a SQL eredmenybol megprobal eszkoz/item neveket kinyerni. Ezekkel a nevekkel celzott RAG keresest futtat, majd a vegso LLM promptban egyszerre szerepel a SQL eredmeny es a dokumentacios kontextus.

HYBRID ag visszaterese:

```python
{
    "ok": True,
    "question": question,
    "route": "HYBRID",
    "sql": safe_sql,
    "result": result,
    "answer": answer,
    "matched_names": matched_names,
}
```

## Modulok szerepe roviden

### `app/web/simple_server.py`

Streamlit frontend. A user kerdest bekero UI innen hivja a `handle_question()` fuggvenyt, majd a kapott dict alapjan megjeleniti a valaszt, route-ot, SQL-t es debug adatokat.

### `main.py`

Konzolos belepesi pont. Terminalbol ker be egy kerdest, meghivja a `handle_question()` fuggvenyt, majd kiirja az eredmenyeket.

### `app/orchestration/orchestrator.py`

A kozponti folyamatiranyito. Meghivja az input ellenorzest, routert, SQL/RAG/HYBRID agakat, majd egyseges valasz dictet ad vissza.

### `app/services/routing_service.py`

LLM-alapu router. Bemenete a user kerdes, kimenete `SQL`, `RAG` vagy `HYBRID`.

### `app/services/sql_generation_service.py`

Text-to-SQL modul. Bemenete a user kerdes, kimenete egy tisztitott SQL string.

### `app/services/schema_service.py`

Sema formatter. A configban levo adatbazis semabol olvashato prompt-reszletet keszit az SQL generatornak.

### `app/services/answer_service.py`

SQL eredmenybol keszit felhasznalobarat valaszt. Bemenete a kerdes, SQL es strukturalt DB eredmeny, kimenete egy szoveges valasz.

### `app/services/llm_service.py`

Kozponti OpenAI chat wrapper. Minden szoveges LLM hivas ezen keresztul megy.

### `app/db/connection.py`

PostgreSQL kapcsolatot nyit `.env` valtozok alapjan. Hiba eseten alkalmazasszintu DB hibat dob.

### `app/db/executor.py`

Lefuttatja a validalt SQL queryt. Visszaadja az oszlopokat, sorokat es a visszaadott sorok szamat.

### `app/security/injection_checks.py`

Elso szintu input filter. Gyanus prompt injection vagy SQL injection mintak eseten megallitja a feldolgozast.

### `app/security/sql_validator.py`

SQL biztonsagi ellenorzes. Csak olvashato queryket enged at, tiltja a mutalo vagy schema-modosito kulcsszavakat.

### `app/security/guardrails.py`

SQL LIMIT vedelem. Gondoskodik rola, hogy a query ne hozzon vissza tul sok sort.

### `app/rag/retrieval/rag_service.py`

RAG valaszgenerator. A dokumentacios chunkokbol kontextust epit, majd LLM-mel valaszt general.

### `app/rag/retrieval/retriever.py`

RAG keresesi logika. Semantic search vagy nev szerinti filterezett keresest indit Qdrantban.

### `app/rag/embedding/embedding_service.py`

Embedding keszito. Szovegbol vektort general OpenAI embedding modellel.

### `app/rag/vector_store/qdrant_client.py`

Qdrant kliens. Collection inicializalas, payload indexeles, upsert es keresesi muveletek.

### `app/rag/ingestion/ingestion_service.py`

Dokumentacio betoltesi pipeline. TXT fajlbol parse-ol, chunkol, embeddinget keszit, majd feltolti Qdrantba.

### `app/rag/ingestion/parser.py`

A `devices.txt` formatumu dokumentaciot eszkozokre es szekciokra bontja.

### `app/rag/ingestion/chunker.py`

A parse-olt eszkoz szekciokbol `RagChunk` objektumokat keszit.

### `app/rag/models/rag_models.py`

Egyszeru dataclass a RAG chunk reprezentaciojahoz.

### `app/errors.py`

Alkalmazasszintu hibak. Ezekbol lehet felhasznalobarat hibauzenetet mutatni a frontenden.

## Fontos config/env fajlok

### `.env`

Lokalis titkok es futasi beallitasok. Tipikus kulcsok:

- `OPENAI_API_KEY`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `DB_HOST`
- `DB_PORT`
- `SQL_QUERY_TIMEOUT_MS`
- `SQL_DEFAULT_LIMIT`
- `SQL_MAX_LIMIT`
- `SQL_MAX_ROWS_RETURNED`
- `QDRANT_URL`
- `QDRANT_API_KEY`
- `QDRANT_COLLECTION`
- `EMBEDDING_MODEL`

### `.env.example`

Minta env fajl. Jelenleg foleg OpenAI, DB es SQL limiteket mutat.

### `config/schema.json`

Az adatbazis tabla- es oszlopszerkezete. Ezt kapja meg a text-to-SQL prompt.

### `config/schema_descriptions.yaml`

Emberi leirasok a tablakhoz es oszlopokhoz. Segit az LLM-nek jobban erteni a semat.

### `config/column_mapping.yaml`

Jelenleg uresnek tunik. Valoszinuleg jovobeli oszlopnev-mappinghez lett fenntartva.

### `app/prompts/text_to_sql.txt`

Prompt template az SQL generalashoz. Ebbe kerul be a schema es a user kerdes.

### `app/prompts/answer_generation.txt`

Prompt template a SQL eredmeny magyar nyelvu megvalaszolasahoz.

### `app/rag/data/devices.txt`

RAG dokumentacios adatforras. Ezt lehet ingestion soran Qdrantba tolteni.

## Hogyan kell futtatni?

### Streamlit UI

A jelenlegi UI alapjan:

```bash
python -m streamlit run app/web/simple_server.py
```

### Konzolos mod

```bash
python main.py
```

### Tesztek

```bash
python -m pytest
```

### RAG ingestion

A pipeline fuggvenye:

```python
from app.rag.ingestion.ingestion_service import ingest_devices

ingest_devices("app/rag/data/devices.txt")
```

Ehhez OpenAI embedding eleres es Qdrant konfiguracio is kell.

## Javasolt debug/log pontok

Ezeket erdemes lehet kesobb betenni, de csak kulon modositas utan:

- `simple_server.py`: user `question`
- `orchestrator.py`: prompt injection check eredmenye
- `orchestrator.py`: `route`
- `sql_generation_service.py`: raw generated SQL
- `orchestrator.py`: validated/safe SQL
- `db/executor.py`: SQL result `row_count`
- `orchestrator.py`: HYBRID `matched_names`
- `retriever.py`: retrieved chunk count
- `rag_service.py`: built RAG context hossza vagy chunk nevei
- `answer_service.py` / `rag_service.py`: final answer eleje vagy hossza

Fontos: erdemes `logging` modult hasznalni `print()` helyett, mert kesobb ki-be kapcsolhato es szintezheto.

## Gyanus pontok

### `scripts/run_webapp.py`

Ez ezt importalja:

```python
from app.web.simple_server import run_server
```

Viszont a jelenlegi `app/web/simple_server.py` Streamlit appkent mukodik, es nem tartalmaz `run_server()` fuggvenyt. Ez a script valoszinuleg egy regi, sima HTTP serveres verziohoz tartozik.

### README technologia lista

A README FastAPI-t emlit, de a jelenlegi futtathato frontend Streamlit. Lehet, hogy a README regebbi architekturara utal.

### Encoding megjelenites

Nehany fajlban a magyar ekezetek es emoji karakterek hibasan jelennek meg a terminal outputban. Ez lehet csak terminal encoding problema, de dokumentacio/UI szovegeknel erdemes figyelni ra.

### Qdrant env valtozok

A kod hasznal `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION` valtozokat, de a `.env.example` jelenlegi tartalmaban ezek nem szerepelnek.

### `column_mapping.yaml`

A fajl jelenleg uresnek tunik. Ha nem hasznalja semmi, akkor ez csak kesobbi terv vagy maradvany lehet.
