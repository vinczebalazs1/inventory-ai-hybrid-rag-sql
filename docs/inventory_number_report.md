# Leltáriszám-alapú rekordazonosítás — megvalósítási riport

**Ellenőrzés: 2026-10-17. Algoritmusverzió: 1.1.**

A kód, az integráció, a tesztek, az offline mérés és a migráció elkészült.
**Az üzleti adatbázisban az egyediség még nincs bevezetve:** 8 duplikált leltári
szám akadályozza. Az üzleti adatokat és sémát nem módosítottam. A migráció csak
adatgazdai ellenőrzés és külön explicit jóváhagyás után alkalmazható.

## A. Módosított és új fájlok

| Fájl vagy csoport | Változás |
|---|---|
| `app/record_matching/repository.py` | Elsődleges leltáriszám-lekérdezés; külön másodlagos kulcs; célzott korai befejezés; átfedő találatok megőrzése; szakaszmérés |
| `app/record_matching/candidate_service.py` | A pontos leltári szám előnyt kap a cikkszámos/névalapú jelöltekkel szemben |
| `app/record_matching/matching_engine.py` | `inventory_number_exact` stratégia; duplikált leltári számnál nincs önkényes feloldás; végleges azonosságjelzés |
| `app/record_matching/models.py` | Opcionális keresési szakaszok, azonosság- és globális keresésjelzés; jelölthöz kötött eltérések/javaslatok |
| `app/record_matching/preparation.py` | Hibás, megadott azonosítót nem lehet másik azonosító javára figyelmen kívül hagyni |
| `app/record_matching/comparison_service.py` | A mezőeltérések jelöltsorszámot is megőriznek |
| `app/record_matching/reconciliation_service.py` | Bizonytalan leltáriszám-jelöltek összehasonlítása is látható |
| `app/record_matching/suggestion_engine.py` | Nem igazolt célhoz külön, kötelezően ellenőrizendő frissítési lehetőség; szigorú globális keresési feltétel az új rekordhoz |
| `app/record_matching/inventory_audit.py` | Új read-only adataudit, duplikációk és normalizálási ütközések külön |
| `app/web/reconciliation_preview.py` | Magyar leltáriszám-/egyediség-magyarázat, magyar stratégiák és mezőstátuszok; technikai azonosítók debugban |
| `config/schema_descriptions.yaml` | A cikkszám nem automatikusan egyedi; a leltári szám nem Service Tag |
| `app/evaluation/{dataset,runner,metrics,_build_fixture}.py` | A termelési keresés vezérlésének újrahasználata, 16 új kézi eset, szakaszmérés, kulcsállapot szerinti riport, fájlonkénti lenyomat |
| `scripts/audit_inventory_numbers.py` | Parancssori audit, menthető riport, egyértelmű blokkolási hibakód |
| `scripts/verify_matching_report.py` | Az aktuális forrás- és adatkészlet-hash ellenőrzése |
| `migrations/001_inventory_number_unique.sql` | Előellenőrzött, külön alkalmazható, tranzakciós UNIQUE index |
| `migrations/001_inventory_number_unique_rollback.sql` | Csak a migráció saját indexét érintő visszaállítás |
| `tests/test_inventory_identity.py` | Új üzleti elfogadási és kompatibilitási tesztek |
| `tests/test_matching_postgres.py` | Valódi izolált DB: elsődleges keresés, migráció, rollback, audit, injection, DOCX-integráció, időmérés |
| `tests/test_reconciliation_ui.py` | A magyar megjelenítés, elsődleges kulcs és bizonytalan jelöltek ellenőrzése |
| `tests/test_matching_evaluation.py`, `tests/fixtures/matching_evaluation.json` | 74 esetes benchmark, a korábbi esetek megtartásával |
| `README.md`, `PROJECT_MAP.md`, `docs/record_reconciliation.md` | Aktuális működés, fájlok és élesítés feltételei |
| `docs/record_matching_evaluation.md` | Friss mérési módszer, tényleges eredmények és korlátok |
| `docs/inventory_number_migration.md`, ez a riport | Adatminőségi akadályok, alkalmazás, rollback, elfogadási ellenőrzés |
| `docs/record_reconciliation_report.md` | A korábbi riport történeti jelölése és hivatkozás az aktuálisra |
| `evaluation/results/` | Friss teszt-, audit-, offline és izolált időmérési bizonyítékok |
| `examples/inventory_number/` | Két kézzel kipróbálható DOCX-minta |

A feladat kezdetén már módosított `app/services/llm_service.py` és a meglévő,
még nem követett `tests/test_llm_service.py` megmaradt; azokat ez a fejlesztés
nem írta át. A Docling/LLM pipeline és a meglévő publikus feldolgozási API megmaradt.

## B. Az új rekordazonosítás

1. Validált `inventory_number` esetén pontos SQL-keresés indul erre a mezőre.
2. Egy megfelelő, érvényes teljes UNIQUE index és egyetlen nem üres találat
   alapján a meglévő kulcs lehet a stabil rekordhivatkozás.
3. A dokumentumbeli többi azonosító egyezését is ellenőrizzük. Eltérő validált
   azonosító vagy kritikus modellkonfliktus továbbra is vétó.
4. Igazolt azonosság esetén `EXACT_MATCH`, `inventory_number_exact`, 1,0 pont
   lehetséges. A cikkszám/alszám nem írja felül a stratégia nevét.
5. A helyszín és más nem azonosító mező eltérése külön összehasonlítás/javaslat;
   nem szünteti meg önmagában az eszköz azonosságát.

Nem keletkezik új ID/UUID, leltári szám vagy `ctid` hivatkozás.
A vezető nullákat, kötőjeleket és a tárolt kulcs betűméretét nem mossuk össze.
A nullable UNIQUE NULL/üres értéke nem ad leltáriszám-azonosságot.

## C. Tényleges adatbázis-audit

Az audit az üzleti adatbázist elérte. `public.inventory_items`: 1000 sor,
11 megfelelő oszlop, `inventory_number text`, igazolt egyedi kulcs nélkül.

| Duplikált leltári szám | Darab |
|---|---:|
| L-16912 | 2 |
| L-17256 | 2 |
| L-17758 | 2 |
| L-36622 | 2 |
| L-45143 | 2 |
| L-54305 | 2 |
| L-66423 | 2 |
| L-88949 | 2 |

NULL, üres, whitespace-only vagy csak whitespace/kisbetűsítés után összeütköző
különböző érték nem volt. Az érintett 16 sor megkülönböztető adatai a
[JSON-auditban](../evaluation/results/inventory_number_audit.json) találhatók.

A szükséges teljes UNIQUE index előkészítve, de **nem alkalmazva**. A migráció
nem oldja meg a duplikációkat; jelenleg biztonságosan leállna rajtuk.
Az indexépítés tranzakciós, rövid ideig blokkolja az írókat; nem használ
`CONCURRENTLY` parancsot tranzakcióblokkban. Az okokat és a nagy táblák korlátait
a [migrációs útmutató](inventory_number_migration.md) részletezi.

## D. Keresési logika és teljesség

Az elsődleges keresést a közös cikkszám és a sok hasonló név nem bővíti fel.
4000 azonos nevű/cikkszámú rekord és 1-es kandidánskorlát mellett is 1 célzott
találat érkezik, teljes elsődleges kereséssel. Nem fut teljes táblás fuzzy keresés.

Ha az elsődleges azonosítás nem bizonyított, a másodlagos keresés és a korábbi
RapidFuzz logika megmarad. `(item_code, sub_code)` csak igazolt összetett kulcsként
bizonyít azonosságot. Duplikált leltári szám esetén a rendszer tartózkodik.

Az `inventory_lookup`, `secondary_lookup`, `fuzzy_search` szakaszok külön jelzik
a futást, teljességet, sorokat, korlátot és időt. Az `identity_verified` a végleges
azonosságot, az `absence_check_complete` a globális újrekord-vizsgálat teljességét
jelöli. Célzott találatnál az utóbbi hamis: nem állítunk teljes táblabejárást.

Az élő `L-94279` próba jelenleg 1 pontos találatot kapott, de UNIQUE hiányában
fuzzy vizsgálat következett, 100-ra korlátozott jelöltlistával. Az eredmény ezért
továbbra is `SEARCH_INCOMPLETE`. Ez az aktuális adatok és garanciák szerinti
helyes működés; a javítás nem hamisít egyediséget a figyelmeztetés eltüntetéséért.

## E. Műveleti javaslatok

| Javaslat | Feltétel |
|---|---|
| ATTACH_DOCUMENT | Igazolt EXACT rekord, stabil kulcs, validált mezők és visszakereshető bizonyíték |
| UPDATE_CANDIDATE, igazolt cél | Az előző feltételek és tényleges összehasonlítható mezőeltérés; mindig ellenőrzés kell |
| UPDATE_CANDIDATE, bizonytalan cél | Pontosan egyező leltári számú, konfliktusmentes jelölt eltérő nem azonosító mezője; nincs igazolt célhivatkozás, csak jelöltsorszám |
| CREATE_RECORD_CANDIDATE | Teljes globális hibrid keresés, NO_MATCH, validált név/azonosító/evidence, közeli duplikációgyanú nélkül |
| MANUAL_REVIEW | Bizonytalanság, hiányos bizonyíték, érvénytelen adat vagy módosítási/létrehozási javaslat |

Az eredeti és javasolt érték, forrásidézet és oldalszám a mezőösszehasonlításban
megmarad. Egyenlő mezőkhöz nem készül felesleges UPDATE. Minden javaslat
`executable=False`; automatikus adatváltoztatás és dokumentumcsatolás nincs.

## F. Tényleges teszteredmény

**202 PASS, 0 FAIL, 0 ERROR, 0 SKIPPED — 44,18 másodperc.**
Bizonyíték: [test_results.xml](../evaluation/results/test_results.xml).
Két `DeprecationWarning` a Docling belső PDF/OCR API-jából származik.

```powershell
venv\Scripts\python -m pytest -q --run-docling-pdf --run-matching-postgres
```

Lefutott a valódi Docling PDF-konverzió és a DOCX → strukturált adatok →
PostgreSQL → egyeztetés → Streamlit lánc. Az utóbbiban a parser/DB/matcher/UI
valódi, az LLM válaszai determinisztikus tesztválaszok. Élő OpenAI-kinyerési
minőséget ebben a feladatban nem mértünk.

| Előírt esetek | Bizonyíték |
|---|---|
| T01–T03 | `test_inventory_identity.py`: leltári szám, azonos mezők, helyszíneltérés |
| T04–T05 | 4000 soros unit és valódi PostgreSQL-keresés, 1-es limit |
| T06–T07 | UNIQUE nélküli javaslatok, duplikált leltári szám és külön jelöltek |
| T08–T09 | NULL, üres kulcs, vezető nullák, betűméret, kötőjelek, tárolt whitespace |
| T10–T12 | Eltérő rekordokra mutató azonosítók, másodlagos összetett kulcs, fuzzy név/helyszín |
| T13–T15 | Hiányzó leltári szám utáni fallback, részleges keresés, adatbázishiba |
| T16–T17 | Hibás/ellentmondó bemenet és Service Tag elutasítása |
| T18–T19 | `test_matching_postgres.py`: duplikációval tiltott migráció; már meglévő index újrahasználata |
| T20 | Kötött SQL-paraméterek, valódi PG-n tárolt injection-karakterlánc sértetlenül |
| T21 | A teljes korábbi SQL/RAG/HYBRID, dokumentumfeldolgozási és LLM-wrapper regressziós tesztcsomag |
| T22 | Régi JSON beolvasása az új Pydantic modellel; Streamlit-gombok, munkamenet és magyar megjelenítés |

A korábbi teszteket nem töröltük. Az új keresési sorrend és a magyar UI miatt
néhány elvárt megjelenítés/találati halmaz frissült, a korábbi ellenőrzések célja megmaradt.
Az izolált PostgreSQL külön ideiglenes klaszter, `127.0.0.1`, véletlen port;
nem használja az üzleti `DB_*` kapcsolatot. A migráció DDL/DML előkészítése
kizárólag ebben a tesztadatbázisban történt.

Két további, üzleti adatbázison futott **read-only smoke próba** a kész DOCX-mintákat
valódi Doclinggal olvasta be; a kinyert mezők/mapping helyett kézzel megadott
strukturált adatot használt. Élő LLM-hívás nem történt. Az egyező minta csak review-t, a `KGK → LIB`
helyszínminta ellenőrizendő UPDATE + review-t adott. A rekord változatlan maradt;
az előtte/utána olvasott helyszín egyaránt `KGK`. A riport kódhash-e is az aktuális
verzióhoz tartozik: [live_inventory_smoke.json](../evaluation/results/live_inventory_smoke.json).

## G. Új kiértékelés és időmérés

74 szintetikus eset, 10 kalibrációs és 64 teszteset; két stratégia, 5 ismétlés.
A korábbi 58 esetet megtartottuk. A végső teszteredmények:

| Metrika | Exact-only | Hybrid |
|---|---:|---:|
| Precision | 1,0000 | 1,0000 |
| Recall | 0,5319 | 0,6596 |
| F1 | 0,6944 | 0,7949 |
| Top-1 accuracy | 0,6383 | 0,8085 |
| Review rate | 0,7969 | 0,7969 |
| Téves kapcsolat / téves automatikus egyezés | 0 / 0 | 0 / 0 |
| Téves újrekord-javaslat | 0 | 0 |

A kulcsállapot szerinti bontás és a fennmaradó referenciaeltérések a
[kiértékelési dokumentációban](record_matching_evaluation.md) szerepelnek.
A régi mérési értékeket nem másoltuk át új eredményként. A kis, ismert
szintetikus készlet nem üzemi pontossági vagy általánosítási garancia.

Külön izolált PostgreSQL-mérés, 4000 sor és 50 ismétlés:

- Korábbi OR lekérdezés: átlag **2,4107 ms**, a jelöltlimit miatt részleges.
- Új elsődleges keresés: átlag **0,5777 ms**, 1 találat, teljes célzott keresés.
- Fuzzy fallback: átlag **37,9985 ms**, korlátos vizsgálat.

Az elsődleges szakasz átlagosan **1,8331 ms-mal rövidebb** volt a korábbi OR
lekérdezésnél. Ez azonos izolált kapcsolaton végzett keresési mérés, nem teljes
alkalmazási vagy üzemi terheléses mérés. A fallback más feladatot old meg.

Fájlok: [matching_metrics.json](../evaluation/results/matching_metrics.json),
[matching_cases.csv](../evaluation/results/matching_cases.csv),
[inventory_search_benchmark.json](../evaluation/results/inventory_search_benchmark.json).

Lenyomatok:

```text
implementation_sha256: 5b4b1c6b90a14ed427bfe26d3457bacc72bcb662d9ff7cba4c96a8ab8cda785b
dataset_sha256:        773aaf4da61ec1bafc1f86619e566b004546eb6895795664f7729d500b58d062
```

Újrafuttatás: `python -m scripts.evaluate_matching --repeats 5`;
ellenőrzés: `python -m scripts.verify_matching_report`.

## H. Kézi kipróbálás

1. Indítsd el a felületet:

   ```powershell
   venv\Scripts\python -m streamlit run app/web/simple_server.py
   ```

2. Nyisd meg a **Dokumentum elemzése – PDF / DOCX** panelt.
3. Töltsd fel az [egyező mintát](../examples/inventory_number/egyezo.docx),
   majd **Analyze document**, utána **Egyeztetés az adatbázissal**.
   A minta: `L-94279`, `E0001`, alszám `0`, `Printer`, helyszín `KGK`.
   Ezeket az értékeket a valódi adatbázisban külön read-only lekérdezés igazolta.
4. Próbáld ki a [helyszínváltozás mintáját](../examples/inventory_number/helyszinvaltozas.docx).
   Ebben a dokumentum helyszíne `LIB`, az adatbázisé `KGK`.
5. Ellenőrizd a kinyerés/mapping eredményét, a leltári számot, a helyszín régi/új
   értékét, a bizonyítékot és az ellenőrzési igényt. A minták tesztdokumentumok,
   nem igazolnak tényleges eszközmozgást.

**Jelenleg:** UNIQUE hiányában nincs garantált EXACT; a helyszínváltozás csak
ellenőrizendő lehetőség. A névjelöltek limitje miatt részleges keresés is látható.
**Adatjavítás és jóváhagyott UNIQUE után:** az egyező mintánál EXACT + ATTACH,
a helyszínmintánál EXACT + UPDATE + review várható, teljes táblás fuzzy keresés nélkül,
ha a dokumentumkinyerés és bizonyítékellenőrzés is sikeres.
A debug JSON külön megmutatja a keresési szakaszokat.

## I. Hátralévő teendők és Definition of Done

| Feltétel | Állapot |
|---|---|
| Leltári szám az elsődleges mező | Kész, tesztelt |
| Tényleges adatbázis-egyediség ellenőrizhető | Kész, élő audit is futott |
| Biztonságos UNIQUE migráció | Elkészült, izolált PostgreSQL-en tesztelt |
| Migráció nem fut automatikusan | Teljesül; üzleti adatbázison nem futott |
| UNIQUE mellett EXACT, új ID nélkül | Izolált DB-n és teljes feldolgozási láncban igazolt |
| Igazolt találatnál nincs felesleges globális fuzzy keresés | Igazolt, 4000 sor/1-es limit |
| Kandidánskorlát nem rontja el az igazolt elsődleges keresést | Igazolt |
| Duplikált leltári számnál nincs önkényes választás | Igazolt |
| Másodlagos és fuzzy keresés | Megmaradt, tesztelt |
| Mezőeltérések | Igazolt és bizonytalan jelölteknél is tesztelt |
| Dokumentumcsatolási javaslat | Igazolt cél + bizonyíték mellett tesztelt |
| Rekordfrissítési javaslat | Igazolt és csak ellenőrizendő célhoz külön jelöléssel tesztelt |
| Újrekord-javaslat | Csak teljes globális keresés és validáció mellett tesztelt |
| Emberi ellenőrzés | Megmaradt |
| Magyar Streamlit-azonosítási magyarázat | AppTesttel ellenőrizve |
| Üzleti DB csak olvasás | Audit és smoke próba; módosítás nem történt |
| Régi és új tesztek | 202 sikeres, 0 kihagyott |
| Offline mérés naprakész | Új futás, friss adat-/kód-hash, külön szakaszmérések |
| Dokumentáció | Frissítve, audit/alkalmazás/rollback és mérési korlátokkal |
| UNIQUE az üzleti adatbázisban | **Nincs alkalmazva: 8 duplikáció, adatgazdai döntés és jóváhagyás szükséges** |
| Élő LLM-kinyerés reprezentatív dokumentumokon | Ebben a feladatban nem mért; külön minőségi értékelés szükséges |

A jóváhagyásra váró konkrét SQL:
[migrations/001_inventory_number_unique.sql](../migrations/001_inventory_number_unique.sql).
Alkalmazás előtt a duplikációkat embernek kell tisztáznia, majd új audit szükséges.
A feltöltési és egyeztetési folyamat sem most, sem a migráció után nem fog
automatikusan üzleti rekordot módosítani.
