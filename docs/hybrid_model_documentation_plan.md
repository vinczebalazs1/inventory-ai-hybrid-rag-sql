# InventoryAI – modellhez kapcsolt HYBRID dokumentáció terve

**Állapot: terv, 2026-11-08.** Élő PostgreSQL- és Qdrant-lekérdezéssel ellenőrizve; ebben a körben nincs embedding/LLM-hívás, feltöltés, adatbázis- vagy alkalmazáskód-módosítás. Csak ez az új tervdokumentum készül.

**Javaslat:** a jelenlegi clean készletben az `item_code` szolgáljon modellkapcsolóként, a Qdrant `name` pedig az eredeti PostgreSQL-modellnevet tárolja. A verziózott dokumentumjegyzék köti össze a modellt, a fájlt és annak eredetét. A 40 általános chunk megmarad.

## 1. Tényleges modellkészlet

Az alkalmazás kapcsolatával, read-only tranzakcióban az `inventory_ai_clean` adatbázison futott:

```sql
SELECT name, COUNT(*) AS record_count
FROM public.inventory_items
GROUP BY name
ORDER BY name;
```

Külön ellenőrzés: modellenként egyetlen különböző `item_code`, és minden különböző `item_code`-hoz egyetlen modellnév tartozik. Ez **a jelenlegi adatkészlet ténye**, nem általános adatbázis-megszorítás. A cikkszám több fizikai példányon ismétlődik; azok külön azonosítója továbbra is a leltári szám.

| PostgreSQL-modellnév | Modellhez tartozó item_code | Rekord |
|---|---|---:|
| APC Back-UPS Pro BR900 | `BR900` | 15 |
| BenQ MW550 | `MW550` | 20 |
| Brother HL-L5200DW | `HLL5200` | 33 |
| Cisco Catalyst 2960 | `CAT2960` | 20 |
| Cisco Catalyst 9200 | `CAT9200` | 20 |
| Cisco ISR 1100 | `ISR1100` | 15 |
| Dell Latitude 5540 | `LAT5540` | 60 |
| Dell Latitude 5550 | `LAT5550` | 60 |
| Dell OptiPlex 7010 | `OPT7010` | 67 |
| Dell P2422H | `P2422H` | 67 |
| Dell PowerEdge R450 | `R450` | 15 |
| Dell UltraSharp U2723QE | `U2723QE` | 67 |
| Epson EB-FH52 | `EBFH52` | 20 |
| Fujitsu ScanSnap S1300i | `SCANS1300` | 15 |
| HP E24 G4 | `HPE24G4` | 66 |
| HP EliteBook 840 G10 | `EB840G10` | 60 |
| HP EliteDesk 800 G6 | `HP800G6` | 66 |
| HP LaserJet Pro M404dn | `M404DN` | 34 |
| HP LaserJet Pro M405dn | `M405DN` | 33 |
| HP ProBook 450 G10 | `PB450G10` | 60 |
| HPE ProLiant DL360 Gen10 | `DL360G10` | 15 |
| Lenovo ThinkCentre M70q | `TCM70Q` | 67 |
| Lenovo ThinkPad T14 Gen 4 | `T14G4` | 60 |
| MikroTik RB4011 | `RB4011` | 15 |
| TP-Link Omada EAP245 | `EAP245` | 15 |
| Ubiquiti UniFi U6 Pro | `U6PRO` | 15 |
| **Összesen: 26 modell** | **26 különböző cikkszám** | **1000** |

Minden sorhoz egy `data/model_documentation/synthetic/<item_code>.synthetic.txt` tesztdokumentumot javaslok. Ez 26 dokumentumterv, **nem 26 már meglévő kézikönyv**.

## 2. Helyben elérhető források

| Ellenőrzött forrás | Felhasználhatóság |
|---|---|
| `app/rag/data/devices.txt` | 10 általános eszköztípus, 40 chunk. Megőrzendő általános tudástár; nem igazol modellfüggő állításokat. |
| `data/synthetic/documents/D01–D16.pdf/.docx` | 32 szintetikus leltári adatlap, az egyeztetési tesztekhez. Nem használati/karbantartási kézikönyvek; nem részei a tervezett feltöltésnek. |
| `examples/inventory_number/*.docx` | Két leltári tesztminta, nem modellkézikönyv. |
| `architecture.pdf`, `docs/*.md` | Alkalmazásarchitektúra, fejlesztési és mérési dokumentáció. |
| `app/test_data/catalog.py` | A szintetikus készlet modellnevei és kategóriái; árai/dátumai nem gyártói specifikációk. |
| `app/document_processing.zip` | Python-modul és bytecode; nincs benne kézikönyv. |

Az ignorált fájlokra kiterjedő keresésben további D01–D16 tesztmásolatok és Docling OCR-segédfájlok szerepeltek. **A projektben a 26 modell egyikéhez sem találtam ellenőrizhető eredetű valódi használati kézikönyvet.** Ez a helyi projekt vizsgálata; internetes gyártói dokumentumgyűjtés most nem történt.

## 3. A tervezett dokumentumkészlet

Minden modellhez egy rövid, magyar **SZINTETIKUS TESZTDOKUMENTÁCIÓ – NEM GYÁRTÓI ÚTMUTATÓ** jelölésű TXT készülhet, három szekcióval:

- **Használat:** szimulált üzemeltetési folyamat és annak ellenőrző lépései.
- **Karbantartás:** tesztforgatókönyv szerinti állapotfeljegyzés és hibajegykezelés.
- **Hibaelhárítás:** kitalált teszteset, a dokumentumban megadott teszteljárással és várt kimenettel.

A jelölés a dokumentumban, **minden chunkban**, a payloadban és a megjelenített válaszban is kötelező. Nem kerülhet bele kitalált gyártói hivatkozás, valósnak állított teljesítményadat, portszám, feszültség, firmware-parancs vagy karbantartási előírás. A modellnév a visszakeresési kapcsolat célpontja; a hozzá rendelt teszteljárás nem válik ettől gyártó által igazolt tudássá.

Egy szekcióból egy rövid chunkot tervezve: **26 × 3 = 78 új pont**, a régi 40 mellett később **118 pont**. Ez tervezett mennyiség; most továbbra is 40 pont van. Azonos szöveg 26 átnevezett példánya önmagában nem elég szemantikus minőségtesztnek: a referenciaesetekben külön szekciókat és egyértelműen tesztcélú, dokumentált eljárásazonosítókat kell vizsgálni.

Szükséges új adatfájlok, későbbi megvalósításhoz:

| Javasolt fájl | Feladat |
|---|---|
| `data/model_documentation/catalog.json` | Az élő DB-ből ellenőrzött 26 `item_code ↔ name` pár, verzió és eredet. Nem a rendezési sorszám az azonosító. |
| `data/model_documentation/synthetic/<item_code>.synthetic.txt` | A 26 egyértelműen jelölt tesztdokumentum. |
| `data/model_documentation/manifest.json` | Dokumentumazonosító, modellkapcsolat, fájlút, SHA-256, verzió, szekciók, szintetikus jelölés, eredet. |
| `data/model_documentation/README.md` | Hatókör és a szintetikus adatok értelmezése. |
| `tests/fixtures/hybrid_model_documentation.json` | Külön rögzített kérdések, elvárt modellek/dokumentumok/szekciók és negatív esetek. |

Valódi dokumentum később csak ellenőrzött modellhatókörrel, eredeti forrással, verzióval/oldalszámmal és fájlhash-sel vehető fel. Szintetikus dokumentum forrása helyi tesztfájl, `source_url=null`; nem kitalált gyártói URL.

## 4. Pontos modellkapcsolat és payload

Példa **tervezett** új payload-metaadatokra:

```json
{
  "name": "Dell Latitude 5540",
  "item_code": "LAT5540",
  "corpus_id": "model_docs_v1",
  "doc_id": "synthetic:LAT5540",
  "document_version": "1",
  "section": "troubleshooting",
  "source": "data/model_documentation/synthetic/LAT5540.synthetic.txt",
  "doc_type": "model_txt",
  "is_synthetic": true,
  "source_kind": "synthetic_test",
  "source_url": null
}
```

A tényleges chunkhoz ezen felül `text`, `source_sha256` és a visszakereshető chunkazonosító tartozik. Hash csak a ténylegesen elkészült fájlról készülhet.

A kapcsolat:

```text
SQL inventory_items: item_code + eredeti name
        ↓ ellenőrzött modellkatalógus
Qdrant-filter: item_code + pontos name + corpus_id
        ↓ csak az adott modell dokumentumai
Szekciók szemantikus rangsorolása → forrással jelölt válasz
```

A `name` **pontosan**, a kis- és nagybetűket is megőrizve egyezzen a PostgreSQL `name` értékével. A katalógus feloldhat ellenőrzött normalizált aliasokat, de a payload és a végső szűrő mindig a kanonikus DB-nevet használja. A `LAT5540` és `LAT5550` nem fuzzy egyezés. A név–cikkszám kapcsolat kétértelműsége vagy változása ellenőrzési hibát okozzon, ne automatikus átkötést.

Ez perzisztált, alkalmazásszintű **modell–dokumentum kapcsolat**, a már meglévő SQL-cikkszámmal. Nem SQL-idegen kulcs és nem egyedi fizikai példányhoz csatolt dokumentum; nem igényel PostgreSQL-sémamódosítást.

## 5. Szükséges kódmódosítások – most még nem végrehajtva

| Fájl / metódus | Szükséges változás |
|---|---|
| Új `app/rag/model_catalog.py` | Ellenőrzött név–cikkszám feloldás, ütközés és hiány jelzése. |
| Új `app/rag/ingestion/model_document_loader.py` | Jegyzék és fájlhash ellenőrzése; használat/karbantartás/hibaelhárítás szekcióinak betöltése. A régi TXT-parser jelenleg nem ismer külön maintenance szekciót. |
| `app/rag/models/rag_models.py::RagChunk` | Opcionális modell- és eredetmezők, hogy a régi általános chunkok kompatibilisek maradjanak. |
| `app/rag/ingestion/ingestion_service.py`, `chunker.py` | Új modellhez kötött betöltési út; a modellnevet explicit metaadatból kapja. A jelenlegi általános feltöltés `name=source.lower()` fájlneve nem megfelelő. Az új mezők kerüljenek a payloadba. |
| Új `scripts/ingest_model_documents.py` | Alapértelmezett dry-run: 26 modell, hash-ek, szintetikus címkék, tervezett pontok és ütközések ellenőrzése. Írás csak külön explicit alkalmazással; API-hibánál megállás és részállapot-riport. |
| `app/orchestration/orchestrator.py::_extract_names_from_sql_result` | A névérték `lower()` műveletét megszüntetni; ellenőrzött `name + item_code` modellreferenciákat átadni. Az oszlopnevek normalizálása maradhat. |
| `app/rag/retrieval/rag_service.py::answer_hybrid_details` | Név kisbetűsítése helyett modellfeloldás; modellenként külön találatok és lefedettségi státusz. |
| `app/rag/retrieval/retriever.py::retrieve_by_name` | `name.lower()` helyett pontos kanonikus név, plusz `item_code` és korpuszszűrés. A kérdés vektora egyszer készüljön, több modellnél újrahasználható. |
| `app/rag/vector_store/qdrant_client.py` | A meglévő `name` keyword index marad; a ténylegesen szűrt új mezőkön index: `item_code`, `corpus_id`, `is_synthetic`; általános visszaeséshez `doc_type`. Méret/modell változatlan: 3072, Cosine, text-embedding-3-large. |
| `rag_service.py::build_context/build_sources`, `app/web/simple_server.py`, `main.py` | Modellkapcsolat, dokumentumverzió, szintetikus jelölés és visszakeresési mód továbbadása/megjelenítése. |

Ha a generált SQL nem ad modellnevet vagy azonosítót, a HYBRID nem találhat ki kapcsolatot. Ha van egyértelmű leltári szám/cikkszám, paraméterezett read-only feloldás alkalmazható; azonosító nélküli aggregált eredménynél „modell nem azonosítható” státusz szükséges. A SQL-generálás HYBRID bemenetét/promptszerződését is ehhez kell igazítani, futásidejű ellenőrzéssel.

**Visszaesés:** hiányzó modellkézikönyvnél vagy részleges többmodelles találatnál ezt modellenként jelezni kell. Az általános `devices.txt` külön, általános tanácsként használható (`doc_type=device_txt` szűréssel). A mostani szűretlen szemantikus fallback az új készlet mellett más modell chunkját is visszaadhatná, ezért nem maradhat modellbizonyítékként.

**Szintetikus mód:** javasolt explicit tesztmód, alapértelmezetten kikapcsolva. Normál RAG és HYBRID keresésből a `is_synthetic=true` pontok kizárandók; tesztmódban látható jelöléssel használhatók. A régi, ilyen mező nélküli 40 pont marad elérhető. Amíg nincs valódi kézikönyv, normál módban nem állítható 26/26 valódi dokumentációs lefedettség.

## 6. Adatmegőrzés és ellenőrzés

A későbbi betöltés kizárólag új pontokat adjon hozzá, külön UUID-névtérrel; az azonosító alapja `corpus_id + doc_id + document_version + section + chunk_index`. Nem kell törölni/újralétrehozni a kollekciót vagy újraindexelni a 40 régi pontot. Azonos dokumentumverzió újrafuttatása nem hozhat duplikátumot; megváltozott tartalom azonos verzió alatt legyen hiba. Dokumentumverzió-váltáskor a jegyzék mondja meg az aktív verziót, a keresés ne keverje a régivel.

Javasolt, **még nem lefuttatott** ellenőrzések:

1. Offline séma- és katalógusteszt: 26/26 DB-modell lefedett, cikkszám/név egyezik, minden új dokumentum és chunk szintetikus jelölésű.
2. Lokális Qdrant-teszt rögzített tesztvektorokkal, külső API nélkül: pontos névszűrés, cikkszám-szűrés, 5540/5550 és M404dn/M405dn elkülönítése, hiányzó modell, hibás kapcsolat, többmodell-részlefedettség, szintetikus mód ki/be.
3. Későbbi engedélyezett feltöltés után: 78 új/118 összes pont, ha a tervezett chunkolás valósul meg; a régi 40 pont azonosítója, teljes payloadja és vektora változatlan. PostgreSQL teljes rekordhash változatlan.
4. Külön rögzített referencia: 26 modell × 3 témakör = 78 keresési eset, plusz negatív és többmodelles esetek. Mérendő: modellkapcsolat helyessége, szekció-hit@k/recall@k, más modellből származó találatok, fallback arány, forrásjelölés és szintetikus jelölés helyessége.
5. SQL/RAG/HYBRID regresszió; néhány élő végponttól végpontig próba csak későbbi engedélyezett körben. A tesztekhez forrás-, dokumentum- és fixture-manifest, modellverzió, dátum és futtatási konfiguráció rögzítendő.

A szakdolgozatban védhető állítás: **„26 modellhez rendelt, szintetikus dokumentumkészleten ellenőrzött modellkapcsolat és HYBRID visszakeresés.”** Ez nem bizonyítja a valódi termékismeret vagy gyártói hibaelhárítás helyességét. A korábbi rekordegyeztetési metrikáktól külön mérés szükséges.

A mostani olvasási vizsgálat kiinduló állapota: 1000 PostgreSQL-rekord, 40 Qdrant-pont. A teljes leltártartalom hash-e: `35b4d94c418fe16ee1a899c0b22a39fc6d0f8e30e38c940400795ac79768486e`. A korábbi riportokat és konfigurációkat megőrizzük; az itt felsorolt új adat- és kódfájlok jövőbeli munkatételek.

**Záró ellenőrzés:** a PostgreSQL teljes rekordhash-e változatlan; mind a 40 Qdrant-pont azonosítója, payloadja és vektora egyezik a vizsgálat elején visszaolvasott értékkel. Mind a 220 korábban rögzített projekt-/konfigurációs fájl változatlan. Ebben a körben csak ez a tervdokumentum jött létre.

