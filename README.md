# InventoryAI

Természetes nyelvű leltárkeresés, dokumentumalapú válaszadás és PDF/DOCX dokumentumokból kinyert adatok egyeztetése PostgreSQL-rekordokkal.

A projekt működő szakdolgozati prototípus, Streamlit-felülettel és kérdésfeldolgozó CLI-vel. A dokumentumelemzés és a rekordegyeztetés **nem módosítja a PostgreSQL adatait**, és nem hajt végre tényleges dokumentumcsatolást. A külön RAG-tudástárfeltöltés viszont Qdrantba ír.

## Funkciók

| Funkció | Működés |
|---|---|
| **SQL** | Természetes nyelvű kérdés → LLM által generált SQL → validáció és korlátok → PostgreSQL → szöveges válasz. |
| **RAG** | Embeddingalapú dokumentumkeresés Qdrantban, válaszkészítés és forrásmegjelenítés. |
| **HYBRID** | Az SQL-eredmény tényleges `name` és `item_code` párjához rendelt gyártói dokumentáció visszakeresése. |
| **PDF/DOCX elemzés** | Docling → LLM-es mezőkinyerés → séma szerinti megfeleltetés → determinisztikus normalizálás és validáció. |
| **Rekordegyeztetés** | Eszközcsoportosítás, csak olvasó PostgreSQL-keresés, jelöltrangsorolás, mezőösszehasonlítás, javaslatok és CSV-export. |

## Telepítés

A parancsok **Windows PowerShellben, a projekt gyökeréből** futtathatók. A dokumentált fejlesztői környezet Python 3.11.9; a példák a `venv` könyvtárat használják, aktiválás nélkül.

Új környezet és alkalmazásfüggőségek:

```powershell
py -3.11 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

Tesztekhez és szintetikus PDF/DOCX dokumentumok generálásához:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Már meglévő `.env` fájlt őrizz meg. Új telepítésnél:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

## Konfiguráció

| Változó | Jelentés |
|---|---|
| `OPENAI_API_KEY` | Az LLM- és embeddinghívások API-kulcsa. |
| `DB_NAME` | A jelenlegi clean környezetben `inventory_ai_clean`. |
| `DB_HOST`, `DB_PORT` | A PostgreSQL címe és portja; helyben jellemzően `localhost`, `5432`. |
| `DB_USER`, `DB_PASSWORD` | A leltárt és a szükséges sémaadatokat olvasni képes felhasználó. |
| `QDRANT_URL`, `QDRANT_API_KEY` | A saját Qdrant cluster endpointja és kulcsa. |
| `QDRANT_COLLECTION` | Alapértéke `devices`; a gyártói kézikönyvek betöltője ezt a nevet várja. |

A `.env.example` jelenleg nem tartalmazza a Qdrant-változókat; a saját `.env` fájlodat ezekkel is egészítsd ki. Kulcsot vagy jelszót ne adj a Githez.

- A dokumentumfeldolgozás modellje `DOCUMENT_LLM_MODEL`, alapértéke `gpt-6-luna`. Ez nem globális modellválasztó: a kérdésfeldolgozás közös LLM-függvényének külön alapértéke van, jelenleg szintén `gpt-6-luna`.
- Az `EMBEDDING_MODEL` alapértéke `text-embedding-3-large`; a kollekció **3072 dimenziós, Cosine** vektorokat használ. Más modellre nem lehet pusztán konfigurációcserével átállni.
- A `DOCUMENT_*`, `MATCHING_*` és `SQL_*` korlátok mintái a `.env.example` fájlban szerepelnek.
- A mintában a `PGOPTIONS='-c default_transaction_read_only=on'` kapcsolati írásvédelmet állít be. Az egyeztető repository ettől függetlenül is csak olvasó tranzakciót nyit.

A **Streamlit a projektgyökér `.env` fájlját a szolgáltatások importálása előtt tölti be; annak értékei felülírják az örökölt terminálváltozókat**. Módosítás után a teljes Streamlit folyamatot indítsd újra. A CLI és a segédprogramok nem alkalmazzák ezt az általános felülírást; ott az örökölt környezet is számít.

### Adatbázis és Docling

Az alkalmazás indítása nem hozza létre és nem tölti fel az adatbázist. Új gépen kövesd a [clean adatbázis telepítési útmutatóját](docs/clean_inventory_database.md). Az adminisztratív létrehozás, migráció és import külön eszközökben, `.env.clean.local` konfigurációval történik; íráshoz `--apply --confirm-db inventory_ai_clean` szükséges. A működő adatbázisra nem kell újra importálni a készletet.

PDF/OCR modellek előkészítése:

```powershell
.\venv\Scripts\python.exe -m scripts.prepare_docling_models
```

A parancs internetkapcsolattal letölti a modelleket az ignorált `.cache/docling/` könyvtárba, vagy a `DOCUMENT_ARTIFACTS_PATH` által megadott helyre. Nem indít LLM-hívást vagy adatbázis-feltöltést. A csomagverziókat a `requirements.txt` rögzíti, köztük a Docling, RapidOCR és Qdrant kliens verzióját.

## Indítás

```powershell
.\venv\Scripts\python.exe -m streamlit run app/web/simple_server.py --server.address 127.0.0.1 --server.port 8501
```

Böngésző: **[http://127.0.0.1:8501](http://127.0.0.1:8501)**.

A kérdést az **Ask a question** mezőbe írd, majd válaszd a **Run analysis** gombot. A SQL/RAG/HYBRID útvonalat a rendszer választja ki. A **Show debug** kapcsoló további technikai részleteket mutat.

CLI, ugyanahhoz a kérdésfeldolgozó belépési ponthoz:

```powershell
.\venv\Scripts\python.exe main.py
```

Az SQL-kérdések is használnak élő LLM-hívásokat. A RAG/HYBRID keresés embeddinghívást is igényelhet. Ezek API-költséggel járhatnak.

## Dokumentumelemzés és rekordegyeztetés

1. Nyisd le a **Dokumentum elemzése – PDF / DOCX** panelt.
2. Az **Elemzendő dokumentum** feltöltőben válassz PDF- vagy DOCX-fájlt.
3. Az **Analyze document** gomb Docling-feldolgozást és élő LLM-es kinyerést/megfeleltetést indít.
4. Ellenőrizd a **Mapped fields**, **Unmapped fields** és **Validation issues** táblázatokat.
5. Az **Egyeztetés az adatbázissal** a már elkészült elemzést hasonlítja össze a PostgreSQL adataival, új LLM- vagy embeddinghívás nélkül.
6. Nézd át az eszközcsoportokat, jelölteket, mezőeltéréseket és javaslatokat. A megjelenített adatok CSV-ben letölthetők.

A feldolgozó alapkorlátja 25 MiB és 200 oldal. A nyers értékek és a forrásidézetek megmaradnak; a PDF-oldalszám a parserből származik, DOCX-hez nem készül kitalált oldalszám.

A stabilizált feldolgozás:

- megőrzi a külön mezőelőfordulásokat; ugyanaz a leltári szám több oldalon egy eszközcsoportot jelent;
- több egyértelmű fizikai azonosítónál csoportonként egyeztet, bizonytalan mező-hozzárendelésnél kézi ellenőrzést kér;
- elkülöníti a nyilvántartott értékeket, számításokat és a célsémához nem kapcsolható műszaki adatokat;
- támogatja a szabályos magyar számcsoportosítást, Ft/HUF jelöléseket, mennyiségi egységeket és dátumformátumokat, az előjel és a nulla megőrzésével;
- megkülönbözteti a hiányzó, ismeretlen, hibás, belsőleg ellentmondó és bizonytalan OCR-értékeket;
- külön számolja az eltérő előfordulásokat és az egyedi eltérő mezőket.

Az elsődleges fizikai azonosító az **`inventory_number`**. Pontos leltári találat mellett is lehet helyszíneltérés vagy kritikus cikkszám-/modellkonfliktus; az azonosítás és az elfogadhatóság külön információ. A hasonlósági pontszám nem valószínűség. Az eszköznév vagy a több példányon ismétlődő `item_code` önmagában nem igazol fizikai rekordazonosságot.

A `SEARCH_INCOMPLETE` nem bizonyítja a rekord hiányát. Az `EXACT_MATCH` sem jelenti valamennyi mező egyezését. A csatolás, frissítés, új rekord és emberi ellenőrzés **javaslatok**: nincs végrehajtó vagy tartós jóváhagyási folyamat. Az eredmény munkamenetben marad; új fájl vagy új elemzés érvényteleníti.

Részletek: [aktuális implementációs dokumentáció](docs/thesis_document_processing_final_implementation.md).

## RAG és gyártói dokumentáció

A **Knowledge base upload → Upload PDF or TXT → Add to knowledge base** az általános RAG-feltöltés. Embeddingeket készít és Qdrantba ír. Nem futtat leltári egyeztetést, és a feltöltést nem kapcsolja automatikusan fizikai eszközhöz vagy ellenőrzött gyártói modellhez.

Az `app/rag/data/devices.txt` 10 általános eszköztípus leírását adja, 40 szekcióalapú chunkkal. A modellhez kötött HYBRID külön [dokumentumjegyzéket](data/model_manuals/manifest.json) használ:

| PostgreSQL-modellnév | `item_code` | Ellenőrzött gyártói részletek |
|---|---|---|
| Dell P2422H | `P2422H` | Biztonság, tisztítás, önteszt. |
| Brother HL-L5200DW | `HLL5200` | Papírbetöltés, kezdeti hibakeresés, No Paper hiba. |
| Epson EB-FH52 | `EBFH52` | Karbantartás, tisztítás, légszűrőtisztítás kiválasztott részei. |

A modellkeresés a pontos **`name` ÉS `item_code`**, dokumentumtípus és forrásfájlhash alapján szűr. A források gyártói URL-t és 1-től számolt PDF-oldalt tartalmaznak. Hiányzó dokumentáció vagy hibás modellpár esetén ezt jelzi; más modell kézikönyvét nem használja helyettesítőként. Az általános források a RAG ágban továbbra is elérhetők, külön jelöléssel.

A [2026-11-08-i integrációs riport](docs/thesis_hybrid_integration_result.md) **40 általános + 11 gyártói = 51 pontot** igazolt. Ez dátumozott ellenőrzés, nem a mindenkori clusterállapot automatikus igazolása. Új checkout nem tartalmazza a távoli kollekciót vagy a teljes kézikönyveket.

Új, üres tudástárban az általános forrás betöltése a meglévő folyamattal indítható. Ez **élő embeddinghívásokat és Qdrant-írást** végez; már feltöltött tudástárnál nem része az alkalmazás szokásos indításának:

```powershell
.\venv\Scripts\python.exe -B -c "from app.rag.ingestion.ingestion_service import ingest_devices; ingest_devices('app/rag/data/devices.txt')"
```

A PDF-ek helyi, ignorált helye `.cache/official_manuals/`; az URL-eket, hash-eket és kiválasztott oldalakat a jegyzék tartalmazza. [Előkészítési és betöltési útmutató](data/model_manuals/README.md). A betöltő idempotens: azonos pontot kihagy, eltérő meglévő payloadot nem ír felül.

Előkészített PDF-ekkel, elérhető clean adatbázissal és meglévő `devices` kollekcióval:

```powershell
$manualReport = ".cache/manual-dry-run-$([guid]::NewGuid().ToString('N')).json"
.\venv\Scripts\python.exe -B -m scripts.ingest_model_manuals --report $manualReport
```

A dry-run külső szolgáltatásokat olvas, de nem készít embeddinget és nem ír pontokat. Feltöltéshez külön `--apply` és új riportfájl kell. A teljes PDF-eket és kivonataikat ne publikáld a repositoryban. A lefedettség három modell kiválasztott fejezeteire korlátozódik.

## Tesztadatok és kiértékelés

A `data/synthetic/` verziózott készlet **1000 szintetikus fizikai eszközt**, 26 modellt és 10 kategóriát tartalmaz. A leltári szám egyedi, a cikkszám ismétlődhet, a mennyiség rekordonként 1. A `data/synthetic/documents/` alatt a D01–D16 forgatókönyvek PDF- és DOCX-változatai találhatók. Ezek leltári tesztadatlapok, nem gyártói kézikönyvek; nem kerülnek automatikusan Qdrantba.

- [Adatkészlet és generátor](docs/synthetic_inventory_dataset.md)
- [PostgreSQL telepítés és betöltés](docs/clean_inventory_database.md)
- [Rekordegyeztetési mérési módszer](docs/record_matching_evaluation.md)

Offline kiértékelés új könyvtárba, élő LLM és adatbázis nélkül:

```powershell
$evalDir = Join-Path ".cache" ("evaluation-" + [guid]::NewGuid().ToString("N"))
.\venv\Scripts\python.exe -B -m scripts.evaluate_matching --repeats 5 --output "$evalDir/matching"
.\venv\Scripts\python.exe -B -m scripts.evaluate_clean_inventory --dataset data/synthetic --expected-count 1000 --report "$evalDir/matching_offline.json"
```

A clean értékelő referenciaeltérésnél 1-es kilépési kódot ad; a riportban kell elkülöníteni az eltérést a futtatási hibától. Ezek a mérések ismert strukturált mezőkből indulnak, nem az élő LLM dokumentumkinyerési pontosságát mérik. A meglévő `evaluation/` riportokat ne írd felül új futással.

## Automatizált tesztek

Alap tesztkör:

```powershell
.\venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider
```

A valódi PDF-feldolgozás és az izolált PostgreSQL-tesztek külön kapcsolóval indulnak. A PostgreSQL-tesztek saját ideiglenes klasztert hoznak létre és töltenek fel, nem az alkalmazás `inventory_ai_clean` adatbázisát használják. Az `initdb` és `pg_ctl` helye `MATCHING_TEST_PG_BIN` változóval adható meg; alapútvonal: `C:\Program Files\PostgreSQL\18\bin`.

Az eredeti T02 PDF próbájához a `STABILIZATION_T02_PDF` változóban kell megadni a saját fájl teljes útját. Ez a PDF nincs a repositoryban. Hiányzó fájl vagy PostgreSQL-bináris esetén egyes tesztek kihagyást jeleznek; a kapcsolók önmagukban nem garantálnak kihagyásmentes futást.

Bővített futás új riportkönyvtárral:

```powershell
$testDir = Join-Path ".cache" ("tests-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $testDir | Out-Null
$previousCleanReportDir = $env:CLEAN_INVENTORY_REPORT_DIR
$previousBenchmarkOutput = $env:MATCHING_BENCHMARK_OUTPUT
try {
    $env:CLEAN_INVENTORY_REPORT_DIR = Join-Path $testDir "clean_inventory"
    $env:MATCHING_BENCHMARK_OUTPUT = Join-Path $testDir "inventory_search_benchmark.json"
    .\venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider --run-docling-pdf --run-matching-postgres "--junitxml=$testDir/test_results.xml"
}
finally {
    $env:CLEAN_INVENTORY_REPORT_DIR = $previousCleanReportDir
    $env:MATCHING_BENCHMARK_OUTPUT = $previousBenchmarkOutput
}
```

A tesztek LLM-válaszhelyettesítőket és helyi Qdrantot használnak; nem igényelnek élő LLM-/embeddingkéréseket vagy távoli Qdrant-feltöltést. Hiányzó Docling-modellek letöltése történhet.

A [2026-11-14-i mentett JUnit](evaluation/stabilization_2026-11-14/test_results.xml) **515 sikeres, 0 hibás és 0 kihagyott tesztet** rögzít. A körülmények, forrásmanifest és a PDF/OCR-bizonyítékok határa a [stabilizálási jelentésben](docs/document_processing_stabilization_2026-11-14.md) szerepel. Ez korábbi futási eredmény, nem minden új környezetre garantált tesztszám vagy hibátlan élő LLM/OCR-felismerés.

## Projektfelépítés

| Útvonal | Feladat |
|---|---|
| `app/orchestration/`, `app/services/` | Kérdésirányítás, SQL-generálás, LLM-kommunikáció, válaszkészítés. |
| `app/security/`, `app/db/` | Bemenet- és SQL-ellenőrzés, korlátok, PostgreSQL-kapcsolat. |
| `app/rag/` | Feltöltés, embedding, Qdrant-keresés, modellkézikönyvek. |
| `app/document_processing/` | Docling, mezőkinyerés, forráskövetés, megfeleltetés, validáció. |
| `app/record_matching/` | Csoportosítás, keresés, pontozás, összehasonlítás, javaslatok. |
| `app/web/` | Streamlit-kérdezés, dokumentumelőnézet, egyeztetési eredmények, export. |
| `app/evaluation/`, `app/test_data/` | Offline kiértékelés, reprodukálható szintetikus készlet. |
| `config/`, `app/prompts/` | Fájlalapú séma, leírások, LLM-promptsablonok. |
| `data/`, `migrations/`, `scripts/` | Adatkészletek, jegyzék, külön telepítő és segédprogramok. |
| `tests/`, `evaluation/`, `docs/` | Tesztek, dátumozott futási bizonyítékok, dokumentáció. |

## Korlátok és hibakeresés

- **Adatbázishiba:** PostgreSQL szolgáltatás, `DB_*` értékek és az `inventory_ai_clean` megléte. `.env`-módosítás után teljes Streamlit-újraindítás szükséges.
- **AI-hiba:** az alkalmazás által használt kulcs, modellhozzáférés és API-kvóta ellenőrzendő. A 401 hitelesítési hiba nem egyeztetési probléma.
- **Qdrant-hiba:** ellenőrizd az endpointot, kulcsot, kollekciót és a kliens/szerver kompatibilitását. A sikertelen verziólekérdezés önmagában nem bizonyít verzióütközést; a kompatibilitás-ellenőrzés kikapcsolása nem kapcsolati javítás.
- **Hiányos dokumentumeredmény:** nézd át a nyers Docling-szöveget, validációt, forrásidézeteket és OCR-jelzéseket. A hiányzó dokumentumadatokat a rendszer nem tölti vissza a PostgreSQL-ből.

A csoportosítás egyértelmű leltári azonosítókra és forráskapcsolatokra épül; tetszőleges többeszközös elrendezést nem old fel. Az LLM és az OCR hibázhat. Nincs automatikus pénzügyi előjeljavítás, korlátlan rekordkeresés, tényleges csatolás vagy adatbázis-frissítés. A csak olvasó alkalmazáshoz megfelelő adatbázis-jogosultságokat is be kell állítani.

## Részletes dokumentáció

- [Aktuális dokumentumfeldolgozó implementáció](docs/thesis_document_processing_final_implementation.md)
- [Stabilizálás és ellenőrzési korlátok – 2026-11-14](docs/document_processing_stabilization_2026-11-14.md)
- [Gyártói dokumentáció és HYBRID-integráció – 2026-11-08](docs/thesis_hybrid_integration_result.md)
- [Qdrant/RAG helyreállítás – 2026-11-08](docs/rag_restoration_2026-11-08.md)
- [Forráskód és történeti mérési riportok auditja](docs/thesis_source_consistency_audit.md)

A korábbi V1-, rekordegyeztetési és migrációs riportok fejlesztéstörténeti dokumentumok. Az `inventory` adatbázis régi duplikációs auditja nem azonos az `inventory_ai_clean` készlet állapotával. A régi tesztszámokat és metrikákat a hozzájuk tartozó dátummal és forrásverzióval kell értelmezni.
