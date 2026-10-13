# Rekordegyeztető modul: megvalósítási és elfogadási riport

Ellenőrzés dátuma: **2026-10-10**.

## A. Elkészült funkciók

A meglévő dokumentumelemzés `ProcessingResult` eredményéből külön indítható,
determinista, kizárólag olvasó rekordegyeztetés készült. A modul validálja és
előkészíti a mezőket, ellenőrzi a PostgreSQL-sémát és az egyediséget, korlátos
keresést végez, pontozza a jelölteket, jelzi az eltéréseket és tanácsadó
műveleteket állít elő. Konfliktus, több eszköz, közeli jelöltek, érvénytelen
adat, hiányzó evidencia, limit és timeout külön kezeltek.

A Streamlit felület külön indítógombot, jelöltlistát, pontmagyarázatot,
mezőösszehasonlítást, bizonyítékokat, javaslatokat és review-jelzést kapott.
A munkamenet megőrzi az eredményt, új feltöltés/elemzés törli. Hibás
egyeztetéskor a dokumentumelemzés megmarad. Nincs üzleti írást végző gomb.

Elkészült a két stratégiát mérő offline rendszer, 58 kézzel címkézett esettel,
gépi JSON/CSV eredményekkel, identitáshelyes metrikákkal és külön időméréssel.

## B. Architektúra

```text
process_document(bytes, filename)                   meglévő API
              ↓
       ProcessingResult
              ↓
reconcile_document(result)                          új, külön API
              ↓
prepare_document → InventoryRepository.search → MatchingEngine
              ↓
compare_fields → suggest_actions → ReconciliationResult
              ↓
Streamlit review / offline evaluation
```

Az új részben nincs LLM-hívás vagy Text-to-SQL. Az SQL/RAG/HYBRID kérdéskezelés
és a korábbi dokumentumfeldolgozás megmaradt. A repository az eredeti
`get_connection()` függvényt használja kompatibilis, opcionális connect timeouttal.

## C. Fájlok és változtatási kör

**Új alkalmazáskód:**

- `app/record_matching/__init__.py`, `models.py`, `config.py`, `normalization.py`,
  `preparation.py`, `repository.py`, `candidate_service.py`, `matching_engine.py`,
  `comparison_service.py`, `suggestion_engine.py`, `reconciliation_service.py`.
- `app/web/reconciliation_preview.py`.
- `app/evaluation/__init__.py`, `dataset.py`, `metrics.py`, `runner.py`, `_build_fixture.py`.
- `scripts/audit_matching_schema.py`, `scripts/evaluate_matching.py`.

**Új tesztek és adatok:**

- `tests/test_record_repository.py`, `test_candidate_search.py`,
  `test_reconciliation_domain.py`, `test_reconciliation_ui.py`,
  `test_matching_postgres.py`, `test_matching_evaluation.py`,
  `test_matching_evaluation_metrics.py`.
- `tests/fixtures/matching_evaluation.json`.
- `evaluation/results/matching_metrics.json`, `matching_cases.csv`,
  `schema_audit.json`, `test_results.xml`: ténylegesen generált bizonyítékok.

**Módosított meglévő fájlok:**

- `app/db/connection.py`: opcionális, visszafelé kompatibilis kapcsolati timeout.
- `app/web/document_preview.py`: új UI-rész és állapottörlés bekötése.
- `tests/conftest.py`: az izolált PostgreSQL-teszt kapcsolója.
- `requirements.txt`: `rapidfuzz==3.14.6`.
- `.env.example`: validált `MATCHING_*` mintabeállítások.
- `README.md`, `PROJECT_MAP.md`: új modul és futtatási útmutató.

**Dokumentáció:**

- [record_reconciliation.md](record_reconciliation.md): algoritmus, rétegek,
  adatmodellek, pontozás, SQL-biztonság, döntések, UI, konfiguráció és korlátok.
- [record_matching_evaluation.md](record_matching_evaluation.md): adatkészlet,
  referencia, metrikák, tényleges mérés és érvényességi korlátok.
- Ez a tételes elfogadási riport.

A folytatáskor meglévő implementációkat megtartottuk. Nem történt üzleti
migráció, RAG-átírás, régi teszttörlés vagy az eredeti dokumentum-API cseréje.
A módosítások a munkakönyvtárban vannak; külön commit nem készült.

## D. Algoritmus és döntési logika

Pontos azonosítók után összetett mezők és teljes sztringes RapidFuzz
névhasonlóság szolgál a jelöltek kiválasztására. A végső alap-pontszám a
rendelkezésre álló dokumentummezők súlyozott hasonlósága; hiányzó DB-mező
0 pontot kap a változatlan nevezőben. Igazolt egyedi kulcs erősebb bizonyíték,
azonosító- és modellkonfliktus vétót okoz. Közeli jelöltek között nincs
önkényes választás. Minden döntéshez indok és pontfelbontás tartozik.

EXACT kizárólag ténylegesen igazolt egyediséggel és teljes releváns kereséssel
adható. LIKELY mindig review-t igényel. Csak név alapján nincs igazolt azonosság.
Frissítés kizárólag ellenőrzött célrekordhoz, ismert eltérő értékekre, emberi
ellenőrzéssel javasolható. Új rekordhoz teljes hibrid keresés, név, azonosító,
evidencia és duplikációgyanú hiánya kell. Minden javaslat végrehajthatatlan
tanácsadó objektum; adatbázis-változtatás nincs.

## E. Tényleges ellenőrzési eredmények

Végleges teljes parancs:

```powershell
venv\Scripts\python -m pytest -q --run-docling-pdf --run-matching-postgres --tb=short --junitxml=evaluation/results/test_results.xml
```

**149 PASS, 0 FAIL, 0 ERROR, 0 SKIPPED, 34,60 másodperc.**
Gépi bizonyíték: [test_results.xml](../evaluation/results/test_results.xml).
Két `DeprecationWarning` a Docling PDF/OCR belső kódjából származik.

| Csoport | PASS |
|---|---:|
| Meglévő dokumentumfeldolgozás és UI-smoke | 41 |
| Valódi Docling PDF-smoke | 1 |
| Korábbi SQL/RAG/HYBRID és RAG-upload regresszió | 4 |
| Korábbi ingestion, SQL-validáció és biztonsági tesztek | 10 |
| Új egyeztetési domain/normalizálás/delta/javaslat/service | 38 |
| Repository szerződés és SQL-biztonság | 14 |
| Kandidánsválogatás | 6 |
| Új Streamlit-egyeztetési UI | 16 |
| Metrikák helyessége | 10 |
| Teljes offline mérés és adatkészlet | 2 |
| Izolált valódi PostgreSQL-integráció | 7 |
| **Összesen** | **149** |

Az utolsó integrációs teszt valódi DOCX-et konvertál, két mockolt LLM-választ
feldolgoz az eredeti extraction/mapping útvonalon, valódi ideiglenes
PostgreSQL-rekordot egyeztet, majd Streamlit AppTesttel megjeleníti az eredményt.
Ellenőrzi, hogy az LLM nem fut újra, a rerender nem ismétli az egyeztetést,
és az adatbázis rekordja változatlan.

| További ellenőrzés | Státusz és bizonyíték |
|---|---|
| Élő üzleti séma auditja | PASS: kompatibilis 11 oszlop, nincs PK/UNIQUE; `schema_audit.json` |
| Read-only tranzakció | PASS: valódi PG `transaction_read_only=on`; próbált UPDATE elutasítva az izolált DB-n |
| Python fordítás/importok | PASS: compileall és teljes pytest-import |
| Függőségek | PASS: `pip check` → `No broken requirements found` |
| Változtatások formázása | PASS: `git diff --check`, whitespace-hiba nélkül |
| Offline benchmark | PASS: 58 eset, 2 stratégia, 5 ismétlés; döntések determinisztikusak |
| Kötelező ellenőrzést blokkoló körülmény | BLOCKED: nincs |

Az alap `pytest -q` kapcsolók nélkül szándékosan kihagyja a modellfüggő PDF-et
és az izolált PostgreSQL-teszteket. A fenti végleges futás mindkettőt engedélyezte,
ezért nem maradt kihagyott teszt.

Fejlesztés közben a PostgreSQL-tesztindítás Windows alatt örökölt stdout-pipe
miatt timeoutolt (6 setup error). A tesztharness fájlba irányított startup
kimenettel javítva lett, az ideiglenes szerver leállt, és a végleges újrafutások
sikeresek. Ez nem fennmaradó termékhiba.

**Nem igazolt külön üzemi ellenőrzések:** élő OpenAI-válaszok minősége,
élő Qdrant-tal végzett teljes kérdés–válasz folyamat, reprezentatív nagy
adatbázisos terhelés. A regressziós tesztek ezek külső függőségeit mockolják.
Ezeket nem jelentjük élő integrációs PASS-ként.

## F. Mért offline eredmények

48 elkülönített teszteset; részletek a
[mérési dokumentációban](record_matching_evaluation.md#tényleges-eredmények).

| Metrika | Exact-only | Hybrid |
|---|---:|---:|
| Precision | 1,0000 | 1,0000 |
| Recall | 0,5294 | 0,7059 |
| F1 | 0,6923 | 0,8276 |
| Top-1 | 0,6176 | 0,8235 |
| Státuszpontosság | 0,7917 | 0,9167 |
| Delta F1 | 0,7500 | 0,8889 |
| Téves automatikus egyezés | 0 | 0 |
| Hibás újrekord-javaslat | 0 | 0 |

A hibrid 6-tal több helyes javasolt kapcsolatot adott. Mindkét módszer
81,25%-ban igényelt review-t. A hibrid teljes offline átlagideje 0,6248 ms,
a baseline-é 0,4703 ms; a mérés kis memóriabeli leltárakra vonatkozik.
A JSON/CSV további P@K/R@K, FP/FN, státusz-confusion, idő- és volumenadatokat tartalmaz.

Az eredmények nem jelentenek általános üzemi pontosságot. A referencia és az
implementáció közti státusz-/pénznem-/evidenciaszabály-eltéréseket a mérési
dokumentáció feltárja; ezeket nem címkéztük át a metrikák javítása érdekében.

## G. Fennmaradó korlátok

1. **Nincs stabil üzleti kulcs a jelenlegi táblában.** A modul ezt felismeri:
   valószínű jelölteket és eltéréseket adhat, de igazolt célrekordhoz kötött
   csatolási/frissítési javaslatot nem. Ennek megszüntetése külön,
   üzletileg jóváhagyott kulcs-/sématervezés feladata.
2. **A többeszközös dokumentumok konzervatívan blokkoltak.** Általános,
   eszközönkénti entitáscsoportosítás későbbi adatmodell-fejlesztést igényel.
3. **A javaslatok nem hajtódnak végre.** Tartós dokumentumkapcsolat,
   írási API, jogosultság és auditnapló külön fejlesztés lenne.
4. **A fuzzy egyezés nem fizikai azonosság.** Különösen azonos típusú eszközök
   között elengedhetetlen az egyedi azonosító vagy emberi ellenőrzés.
5. **Nagy tábla keresése részleges lehet.** A SQL-tokenelőszűrés kihagyhat
   elírt neveket; a rendszer ezt jelzi, és nem alapoz rá új rekordot.
6. **A mérés szintetikus.** Független, kézzel ellenőrzött valós dokumentumok,
   reprezentatív leltárak és terhelés szükségesek üzemi következtetésekhez.
7. **Az extraction/mapping tévedhet.** A visszakereshető idézet ellenőrzése
   korlátozza a hibát, de nem bizonyítja a szemantikai értelmezést.

## H. Kipróbálás a felületen

```powershell
venv\Scripts\python -m pip install -r requirements-dev.txt
venv\Scripts\python -m streamlit run app/web/simple_server.py
```

1. A meglévő `DB_*` és dokumentumfeldolgozási beállítások legyenek érvényesek.
2. Nyisd ki a **Dokumentum elemzése – PDF / DOCX** részt.
3. Tölts fel egyetlen eszköz adatait tartalmazó PDF/DOCX-et, majd **Analyze document**.
4. Ellenőrizd a mapped/unmapped mezőket és az evidence-t.
5. Kattints az **Egyeztetés az adatbázissal** gombra.
6. Nézd át a státuszt, kandidánsokat, pontmagyarázatot, összehasonlítást és javaslatokat.
7. Új elemzéssel ellenőrizhető az előző egyeztetés törlése. Újrarajzoláskor a meglévő eredmény marad.

Az aktuális kulcs nélküli üzleti táblán az emberi ellenőrzés jelzése várható
viselkedés. A UNIQUE kulcs melletti EXACT/UPDATE útvonalat az izolált tesztek
igazolják, az üzleti séma módosítása nélkül.

## I. Definition of Done — tételes ellenőrzés

**A specifikáció 41 megvalósítási és automatizált ellenőrzési feltétele teljesült.**
Az alábbi jelölések az itt dokumentált tesztkörnyezetre és bizonyítékokra
vonatkoznak. Az üzemi minőség- és terhelésmérés külön korlát marad.

### Backend — 14/14

- [x] Strukturált dokumentumadatból indítható egyeztetés — nyilvános service és végigfutási teszt.
- [x] Működő read-only SQL kandidánskeresés — 7 valódi PG-integrációs teszt.
- [x] Exact identifier matching — T01 és egyedi kulcsos PG-eset.
- [x] Composite matching — összetett kulcs, név+hely/dátum és benchmark-esetek.
- [x] Fuzzy matching — elírásos névtesztek és baseline-összehasonlítás.
- [x] Determinisztikus, magyarázható ranking — sorrendteszt, ismételt benchmark, score breakdown.
- [x] Ambiguity detection — T05/T16 és near-tie példák.
- [x] Azonosítókonfliktus-felismerés — kritikus vétók és eltérő ID-k.
- [x] Mezőszintű összehasonlítás — explicit ötféle összehasonlítási státusz.
- [x] Eltérésfelismerés — helyszín, dátum, mennyiség és pontos decimális összegek.
- [x] Suggestion engine — attach/update/create/review tanácsadó szabályok.
- [x] Human-review logika — hiány, konfliktus, bizonytalanság, módosítás és evidence.
- [x] Strict JSON eredménymodell — Pydantic extra/type/NaN tiltás, JSON round-trip.
- [x] Nincs automatikus üzleti adatbázis-módosítás — read-only SQL és `executable=False`.

### UI — 10/10

- [x] Dokumentum feltölthető — meglévő uploader és callback tesztelve.
- [x] Dokumentum elemezhető — valódi PDF és DOCX, mockolt LLM extraction/mapping.
- [x] Külön indítható az egyeztetés — explicit gombteszt.
- [x] Kandidánsok megjelennek — UI-táblateszt.
- [x] Pontszám és értelmezés megjelenik — rangsorolás, stratégia, nem valószínűségi jelzés.
- [x] Mezőeltérések megjelennek — értékek, evidence és oldalszám.
- [x] Javasolt műveletek megjelennek — külön típus, indok és korlátok.
- [x] Bizonytalanság látható — minden státusz és review-banner tesztelve.
- [x] Új feltöltés törli a régi állapotot — callback és sikeres/hibás újraelemzés tesztelve.
- [x] UI nem ír üzleti adatbázist — végrehajtó gomb nincs, végigfutás után rekord változatlan.

### Quality — 7/7

- [x] Releváns szélső esetek teszteltek — T01–T28 lefedettség az alábbi táblában.
- [x] Korábbi regressziós tesztek sértetlenek — 56 korábbi teszt PASS az opcionális PDF-fel.
- [x] Python fordítás/import működik — compileall és teljes suite.
- [x] Függőségek dokumentáltak — verzióhoz kötött RapidFuzz, requirements és pip check.
- [x] Teljes futtatható tesztcsomag ellenőrzött — 149 PASS, 0 skip a végleges kapcsolókkal.
- [x] Integrációs tesztek státusza pontosan jelentve — valódi és mockolt komponensek elkülönítve.
- [x] Nincs TODO-val helyettesített üzleti implementáció — kódellenőrzés és futó szolgáltatás.

### Thesis readiness — 10/10

- [x] Algoritmus dokumentált.
- [x] Pontszám számítása reprodukálható, konfigurációval és kódlenyomattal.
- [x] Döntési szabályok és biztonsági indokok dokumentáltak.
- [x] Offline adatkészlet rendelkezésre áll — 58 szintetikus eset.
- [x] Futtatható evaluation script rendelkezésre áll.
- [x] Exact-only baseline futtatható.
- [x] Hibrid determinisztikus stratégia ugyanazon bemeneteken mérhető.
- [x] Metrikák gépileg számíthatók, külön definíciótesztekkel.
- [x] Eredmények tényleges futásból származnak — JSON, CSV, JUnit.
- [x] Korlátok és referenciától eltérő döntések dokumentáltak.

### Az eredeti T01–T28 tesztkövetelmények megfeleltetése

A `test_reconciliation_domain.py` a legtöbb teszt nevében viseli az eredeti
azonosítót. Ezek különböznek az evaluation dataset saját `Txx` esetazonosítóitól.

| Követelmény | Automatizált bizonyíték |
|---|---|
| T01–T03 pontos egyezés és delta | Domain exact/location tesztek; DOCX–PG–UI végigfutás |
| T04–T08 fuzzy, több jelölt, új rekord, kevés adat | Domain typo/tie/new/sparse tesztek |
| T09–T13 konfliktus, technika, serial, nullák, több eszköz | Domain konfliktus-, azonosító- és táblázatblokkolás |
| T14–T16 DB-hiba, timeout, duplikált ID | Domain és repository tesztek, valódi PG-timeout |
| T17–T19 hiány/null/pénz | Domain és Decimal/date repository tesztek |
| T20 injection | Kötött paraméteres unit + valódi PG; nincs LLM-hívás a matcherben |
| T21–T23 séma, limit, JSON | Domain, repository, valódi PG és round-trip teszt |
| T24 session state | 16 Streamlit-egyeztetési teszt |
| T25 régi útvonalak | `test_document_regression.py` és meglévő biztonsági/ingestion tesztek |
| T26 read-only | Valódi PG elutasítja az írást; üzleti adatot a teszt nem használ |
| T27 eltérő modell | Domain modellszám-vétó és evaluation esetek |
| T28 evidence hiánya | Hiányzó, hamis és értéket nem tartalmazó idézet tesztjei |
