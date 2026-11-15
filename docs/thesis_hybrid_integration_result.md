# InventoryAI – gyártói dokumentáció és HYBRID-integráció

**Ellenőrzés: 2026-11-08. Eredmény: működő, hárommodellű prototípus.** A `devices` kollekcióba **11 új pont** került; összesen **51 pont** van. A régi **40 pont teljes payloadja és vektora változatlan**. A PostgreSQL 1000 rekordjának teljes tartalmi hash-e is változatlan; sémamódosítás nem történt.

Futási bizonyítékok: [`evaluation/hybrid_integration_2026-11-08_df8b9377/`](../evaluation/hybrid_integration_2026-11-08_df8b9377/). HEAD: `a7bd4278aaa4a7da6aa7375ff1741c6e9107ab83`, a megvalósítás munkakönyvtári módosítás. A végleges forrás-/tesztmanifest és csomaglista: `final_test_environment.json`.

## Feltöltött tartalom

| Modell és cikkszám | Ellenőrzött gyártói részletek, 1-től számolt PDF-oldalak | Új pont |
|---|---|---:|
| Dell P2422H — `P2422H` | 6: biztonság; 33: tisztítás; 69–70: teljes önteszt | 4 |
| Brother HL-L5200DW — `HLL5200` | 9: papírbetöltés; 11: kezdeti hibakeresés; 13: kizárólag a No Paper bejegyzés | 3 |
| Epson EB-FH52 — `EBFH52` | 163–165: karbantartás/tisztítás; 166: légszűrőtisztítás kiválasztott része | 4 |

A [dokumentumjegyzék](../data/model_manuals/manifest.json) tartalmazza a három hivatalos URL-t, PDF-hash-t, modellazonosság bizonyítékát, oldalszámokat és kivágási határokat. A többmodelles specifikációkat, a Brother régiós kellékanyagait és az Epson modellfüggő karbantartási időközeit nem indexeltük. Minden fájl hash-e és modelljelölése ellenőrzött.

A teljes PDF-ek kizárólag az ignorált `.cache/official_manuals/` könyvtárban vannak; nem kerültek a követett repository-fájlok közé. A teljes visszakeresett chunkszövegek helyi ellenőrzési másolata szintén ebben az ignorált könyvtárban van. A megosztható riport pontazonosítót, metaadatot, szöveghash-t és rövid forráselőnézetet tárol.

A beállítás változatlan: **text-embedding-3-large, 3072 dimenzió, Cosine**. Keyword index: `name`, `item_code`, `doc_type`, `source_sha256`. Az új payloadok tartalmazzák a pontos DB-nevet, cikkszámot, szöveget, forrás URL-jét, PDF-oldalát, fájlhash-t és dokumentumtípust.

## Tényleges ellenőrzési eredmények

| Ellenőrzés | Eredmény |
|---|---|
| Dry-run | 11 tervezett új pont; 0 embedding; a kollekció 40 pontos maradt |
| Célzott offline tesztek | **30 passed**; az összes szükséges pozitív/negatív és idempotenciaeset szerepel |
| Végleges regressziós futás, valódi Docling PDF-teszttel | **250 passed, 81 skipped, 0 failure/error**, 41,44 s |
| Ismételt valódi betöltési parancs | **11 meglévő kihagyva; 0 új pont; 0 embeddinghívás**, összesen továbbra is 51 |
| Adatmegőrzés | Mind a régi 40 pont ID/payload/vektor egyezik; PostgreSQL teljes adathash egyezik |

A **81 kihagyás mindegyike** a külön opt-in kapcsolót igénylő izolált PostgreSQL-tesztekhez tartozik. A mostani futásban nem indítottunk adatbázist létrehozó/módosító tesztkört. Két Docling-deprecation figyelmeztetés volt. Ez nem a teljes 331 teszt kihagyás nélküli sikerét jelenti. A korábbi mérési riportok változatlanok.

Élő, tényleges `handle_question` próbák:

| Eset | Eredmény |
|---|---|
| SQL: leltári rekordok száma | Helyes SQL útvonal, **1000** rekord |
| RAG: nem működő dokkolóportok | A `devices.txt` általános tanácsa; a válasz kifejezetten általános, nem modellfüggő információként jelölte |
| Dell, `L-00502`: hely, modell és önteszt | **KANDÓ / Dell P2422H / P2422H**; kizárólag a Dell megfelelő részletei, 6., 69–70. oldali hivatkozással |
| Brother, `L-00703`: hely, modell és No Paper hiba | **KANDÓ / Brother HL-L5200DW / HLL5200**; a papírhiba megfelelő utasításai, PDF 13. oldal |
| Epson, `L-00901`: hely, modell és légszűrőtisztítás | **LIB / Epson EB-FH52 / EBFH52**; a megfelelő tisztítási rész, PDF 166. oldal |
| Dokumentáció nélkül, `L-00001` | **Dell Latitude 5540 / LAT5540**: egyértelmű hiányjelzés, SQL-adatok, üres dokumentumforrás-lista; nincs más modellből származó tanács |
| Szándékosan hibás pár: Dell P2422H + HLL5200 | **identifier_conflict**, 0 találat, 0 embedding/LLM-hívás; külön negatív bemeneti teszt, nem adatbázisba írt rekord |

A [live_checks.json](../evaluation/hybrid_integration_2026-11-08_df8b9377/live_checks.json) rögzíti a pontos kérdéseket, SQL-eket, válaszokat, visszakeresett pontokat, modellazonosítókat és oldalszámokat. Mindhárom dokumentált modellnél a visszakeresett pontok teljes név/cikkszám/URL/hash/oldal metaadata megfelelt a jegyzéknek; a releváns oldal szerepelt a találatok között. A válaszok tartalmi átnézése is megtörtént.

Feltöltés: **11 sikeres embeddinghívás, 2168 token**. Élő próbák: **16 sikeres chatkérés, 9059 token; 4 embeddingkérés, 97 token**. A több hívás a routingból, SQL-generálásból és válaszgenerálásból adódik. Összesen **15 embeddingkérés**, automatikus újrapróbálkozás és API-hiba nélkül.

## Megvalósítás és megváltozott fájlok

Új alkalmazásfájl: `app/rag/manuals.py`; új betöltő: `scripts/ingest_model_manuals.py`; új teszt: `tests/test_model_manuals.py`; új adatok: `data/model_manuals/manifest.json` és `README.md`. További új fájl ez a jelentés és az elkülönített futási bizonyítékkönyvtár.

Módosított meglévő fájlok:

- `app/rag/models/rag_models.py`: opcionális gyártói metaadatok.
- `app/rag/retrieval/retriever.py`: pontos név **ÉS** cikkszám **ÉS** dokumentumtípus **ÉS** fájlhash szerinti keresés, visszaolvasott metaadatok ellenőrzésével.
- `app/rag/retrieval/rag_service.py`: SQL-eredményből származó modellpár, lefedettségi státusz, determinisztikus hiányjelzés, forrás/oldal/általános-gyártói jelölés.
- `app/orchestration/orchestrator.py`, `app/services/sql_generation_service.py`: eredeti névírásmód megőrzése, tényleges `name` és `item_code` kérése a HYBRID SQL-eredményben, státusz továbbadása.
- `app/web/simple_server.py`, `main.py`: modell, cikkszám, gyártói/általános jelölés, PDF-oldal és URL megjelenítése.
- `tests/test_document_regression.py`, `tests/test_inventory_clean_integration.py`: a módosult hívási szerződés és eredeti névírásmód követése a tesztadapterekben.

A kiinduláskor rögzített 221 fájlból **212 változatlan**, a felsorolt 9 meglévő fájl módosult. A `.env`, `.env.example`, `requirements.txt`, régi mérési riportok és PostgreSQL-adatok nem változtak ebben a munkában. A `.env.example` és `requirements.txt` már a feladat előtt módosított állapotban voltak.

## Megmaradt korlátok

- Három modell néhány ellenőrzött fejezetét fedi le, nem a teljes kézikönyveket vagy mind a 26 modellt.
- Modellhez kötött HYBRID-hoz a SQL-eredmény tényleges `name` és `item_code` párja szükséges. Hiányzó/hibás párt a rendszer nem talál ki. A SQL-generálás továbbra is LLM-alapú, ezért ez a néhány sikeres próba nem általános pontosságmérés.
- Dokumentáció hiányában a HYBRID SQL-adatokat és hiányjelzést ad. Általános tanács a RAG ágban továbbra is elérhető; a modellág nem használ szűretlen fallbacket.
- A betöltés változatlan dokumentumokkal idempotens. Új PDF-verzióhoz új hash és fejezetszintű ellenőrzés kell; régi verziót nem töröl automatikusan.
- A Streamlit megjelenítés kódja frissült; élő böngészős felületteszt nem történt. A bizonyíték alkalmazás-belépési ponton futó és offline tesztekből származik.

Végellenőrzés: [final_verification.json](../evaluation/hybrid_integration_2026-11-08_df8b9377/final_verification.json). A mostani eredmények külön funkcionális integrációs bizonyítékok; a korábbi szakdolgozati matchingmetrikákat nem írtuk át és nem minősítjük új HYBRID-mérésnek.
