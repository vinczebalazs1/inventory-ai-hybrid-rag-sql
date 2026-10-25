# Clean tesztadatbázis és adatgenerálás — megvalósítási riport

**Dátum: 2026-10-18. Adatkészlet/generátor: 1.0.**

Ellenőrzési környezet: Windows, Python 3.11.9, PostgreSQL 18, Docling 2.80.0;
PDF/DOCX-generálás: ReportLab 4.4.3 és python-docx 1.2.0.

Az implementáció, a szintetikus adatok, a dokumentumok, az automatizált tesztek
és a reprodukálási útmutatók elkészültek. **311 pytest teszt sikeres.**
A felhasználó helyi `inventory_ai_clean` adatbázisának létrehozása és feltöltése
nem történt meg; a feladat szerint ez külön, explicit jóváhagyást igénylő művelet.
A meglévő `inventory`, `.env`, Qdrant és egyeztetési algoritmus változatlan.

## A. Implementált funkciók

- Tíz kategóriát, 26 modellt és öt helyszínt használó determinisztikus generátor.
- Hivatalos seed 42 / 1000 rekord; kísérleti paraméterezés 1–100 000 rekordig.
- Egyedi `inventory_number`, `quantity=1`, konzisztens típus/cikkszám/ár/dátum.
- Kanonikus CSV és JSON, manifest, visszaolvasás és teljes újragenerálási ellenőrzés.
- Valódi, reprodukálható PDF/DOCX: 16 forgatókönyv × 2 formátum.
- Kimenetektől független ground truth, ismert régi/új mezőértékekkel.
- Külön adatbázis-létrehozási és sémaalkalmazási művelet, alapból dry-run.
- Tranzakciós, paraméterezett batch import; explicit célmegerősítés, tényleges
  adatbázisnév-ellenőrzés, teljes séma/constraint-vizsgálat és tartalom-hash.
- Azonos újrafuttatás és konkurens betöltés biztonságos; eltérő tartalmat nem ír felül.
- SELECT-alapú adatbázis-verifier és géppel feldolgozható JSON-riportok.
- Változatlan InventoryAI matching mérése offline és valódi PostgreSQL mellett.

## B. Új és módosított fájlok

| Fájl/csoport | Feladat |
|---|---|
| `app/test_data/__init__.py` | Új, önálló tesztadat-alrendszer |
| `app/test_data/models.py` | 11 mezős típusos rekord, szigorú generálási beállítások |
| `app/test_data/catalog.py` | Modell–cikkszám–kategória–ár–dátum–élettartam katalógus |
| `app/test_data/generator.py` | Rögzített eloszlás és seed szerinti rekordok |
| `app/test_data/validation.py` | Azonosítók, darabszám, pénzügy, katalógus, dátum és eloszlás |
| `app/test_data/artifacts.py` | Kanonikus CSV/JSON, manifest, hash, betöltési ellenőrzés |
| `app/test_data/documents.py` | PDF/DOCX és független elvárt eredmények |
| `app/test_data/database.py` | DB-célvédelem, létrehozás, migráció, import, verifier |
| `app/test_data/evaluation.py` | Meglévő matcher futtatása, dimenziónkénti elvárás/kimenet összevetés |
| `app/test_data/cli.py` | CLI-k, jóváhagyási kapcsolók, env-konfliktusok, biztonságos hibák |
| `scripts/generate_inventory_data.py` | Offline generálás |
| `scripts/prepare_inventory_database.py` | Külön `create` és `migrate` lépés |
| `scripts/load_inventory_data.py` | Dry-run vagy explicit import |
| `scripts/verify_inventory_data.py` | Csak olvasó ellenőrzés |
| `scripts/evaluate_clean_inventory.py` | Offline vagy read-only PostgreSQL-es dokumentumreferencia-mérés |
| `scripts/verify_clean_inventory_report.py` | Adat-/dokumentum-/aktuális forráslenyomat ellenőrzés |
| `migrations/clean/` | Adatbázis SQL, két idempotens táblamigráció és célzott útmutató |
| `data/synthetic/` | CSV, JSON, manifest, ground truth és 32 dokumentum |
| `tests/test_inventory_data_generator.py` | Offline integritás, determinisztikusság, export, dokumentumok |
| `tests/test_inventory_seed_loader.py` | Env/target/approval és titokmentes hibajelzés |
| `tests/test_inventory_clean_integration.py` | Valódi DB, constraints, rollback, matcher, Docling, UI és olvasószerep |
| `tests/test_inventory_scalability.py` | 10 000 sor és két konkurens importer |
| `evaluation/clean_inventory/` | Külön új teszt- és mérési bizonyítékok |
| `.env.clean.example`, `.env.example` | Új titokmentes minta és kézi app-konfiguráció útmutatása |
| `.gitignore`, `.gitattributes` | A minta követhető, titkos helyi env nem; kanonikus adatsorvégek |
| `requirements-dev.txt` | python-docx 1.2.0 és ReportLab 4.4.3 dokumentumgeneráláshoz |
| `README.md`, `PROJECT_MAP.md` | Új alrendszer és a korábbi audit történeti határa |
| `docs/clean_inventory_database.md` | Adatmodell, telepítés, import, olvasójog és 10 lépéses útmutató |
| `docs/synthetic_inventory_dataset.md` | Generátor, manifest, referencia és reprodukció |
| `docs/clean_inventory_testing.md`, ez a riport | Tesztek, eredmények, korlátok és teljesítés |

A munka tiszta Git-munkakönyvtárból indult. A feladatban felsorolt séma-,
kapcsolat-, matching-, dokumentumfeldolgozó-, migrációs és tesztfájlokat a
megvalósítás előtt ellenőriztem. A `config/column_mapping.yaml` üres, a matching
a tényleges `schema.json`-t használja. A régi rendszer fájljai, az LLM-wrapper,
a 11 oszlop és a meglévő tesztek nem lettek újraírva.

## C. Adatbázisséma

`public.inventory_items`: item_code text, sub_code integer, activation_date date,
name text, purchase_value integer, depreciation integer, current_value integer,
currency text, quantity integer, inventory_number text, location text.

Mind a 11 NOT NULL a clean környezetben. A leltári szám szövegként, vezető nullákkal
tárolt UNIQUE kulcs. A cikkszám nem egyedi. Kilenc CHECK ellenőrzi a leltári formát,
quantity=1-et, három szöveges mező nem üres voltát, három pénzügyi érték
nemnegativitását és a hárombetűs pénznemkódot.

A 11 oszlop és típusuk a tényleges PostgreSQL-sémával automatizáltan egyezett.
Az egyedi indexet a meglévő `InventoryRepository` felismerte. Sem új eszköz-ID,
sem eltérő táblaszerkezet, sem üzleti adatmásolás nincs.
A részletes oszloptábla és megszorítások a [DB-útmutatóban](clean_inventory_database.md) szerepelnek.

## D. Tesztadatok

**1000 sor, 1000 különböző leltári szám, 0 integritási eltérés.**
26 ismétlődő cikkszám/modell; laptop 300, desktop 200, monitor 200, printer 100,
hálózati kategóriák 100, projektor/szerver/egyéb 100.

Seed: 42. Intervallum: 2020-01-01–2026-09-30, modellenkénti későbbi kezdőnappal.
Pénznem: HUF. A szintetikus felhalmozott értékcsökkenés és jelenlegi érték
integer aritmetikával, 2026-09-30 referencianaphoz számolt.

```text
canonical_dataset_sha256:
3a990307ca2e38916cfad1eb3410b3da7609bedcc98e3f43d0717903cdb4982a

ground_truth_sha256:
0102dff4acb9d6417969611de737c513b4199a795c9c5d393ce41b04566e5413

implementation_sha256:
184c273f346a4e9adda1019ef719c156e3c827a5116481af428d66e14c470036
```

Bizonyíték: [dataset manifest](../data/synthetic/manifest.json),
[generálási riport](../evaluation/clean_inventory/generation.json).
Az exportok azonos seedből byte-szinten ismételhetők; a keletkezési timestamp
csak a manifest metaadata, nem része az adathashnek.

## E. Dokumentumok

**16 forgatókönyv, 32 valódi fájl: 16 PDF + 16 DOCX.**
A scenariólista és a reference szerződése:
[szintetikus adatkészlet](synthetic_inventory_dataset.md),
[ground truth](../data/synthetic/ground_truth.json).

Pozitív esetek: létező leltári számok, helyszín/dátum/pénzügy eltérések,
ismétlődő modell másik példánya, magyar formázás/ékezetek.
Negatív esetek: hiányos adat, hiányzó/új azonosító, hibás cikkszám,
modellellentmondás, hibás dátum, több eszköz egy dokumentumban.

Mind a 32 fájl valódi Docling-beolvasása sikeres. D01/D02 mindkét formátuma
a meglévő teljes feldolgozási szolgáltatáson is lefutott, két LLM-tesztválasszal,
majd valódi PostgreSQL-egyeztetéssel. **Ez négy sikeres integrációs próba, élő
OpenAI-kinyerési mérés nélkül.**

## F. Teszteredmények és mérések

| Ellenőrzés | Tényleges eredmény |
|---|---|
| Teljes pytest, régi + új | **311 PASS, 0 FAIL, 0 ERROR, 0 SKIPPED; 134,80 s** |
| Új tesztek | 109; a korábbi 202 teszt megtartva |
| Figyelmeztetések | 6 Docling/RapidOCR DeprecationWarning |
| CSV/JSON és manifest | PASS |
| Tényleges DB-séma/UNIQUE/NOT NULL/CHECK | PASS |
| Hiba a második batch előtt, 250 beszúrás után | PASS: 0 tartós sor, teljes rollback |
| Újrafuttatott seed | PASS: already_loaded, nincs duplikáció |
| Rossz DB-cél / eltérő nem üres tartalom | PASS: elutasítás, nincs felülírás |
| 10 000 sor két egyidejű loaderrel | PASS: egy loaded, egy already_loaded |
| 32 Docling parserpróba | PASS |
| 4 Docling → teszt-LLM → valódi PG próba | PASS |
| 16 üzleti referencia, offline | **14 PASS, 2 FAIL kategóriára** |
| Ugyanaz a 16 eset valódi izolált PG-n | **14 PASS, 2 FAIL kategóriára; egyezik az offline eredménnyel** |
| Élő OpenAI dokumentumkinyerési pontosság | NOT RUN; ebből nem állítunk eredményt |
| Felhasználó helyi clean adatbázisának telepítése | NOT APPLIED; külön jóváhagyásra vár |

A két üzleti referenciaeltérés D05 és D06, mindkettő SEARCH_INCOMPLETE a
100-as kandidánskorlát miatt. Nincs téves csatolás/újrekord-javaslat; az emberi
ellenőrzés megmarad. Nem tüntettük el az eltérést referencia- vagy algoritmus-
módosítással. Részletes magyarázat: [tesztelési dokumentáció](clean_inventory_testing.md).

Egyszeri helyi izolált mérés, nem általános sebességgarancia:

| Művelet | Mért idő |
|---|---:|
| 1000 sor importja, ellenőrzésekkel és committal | 187,47 ms |
| 1000 sor read-only verifikációja | 117,03 ms |
| 10 000 sor generálása | 191,12 ms |
| 10 000 sor importja | 1376,65 ms |
| Egyidejű második loader, várakozással és azonosságvizsgálattal | 1847,31 ms |
| 10 000 sor read-only verifikációja | 668,60 ms |
| Pontos leltári keresés 10 000 sorból | 53,77 ms, 1 beolvasott rekord |

Az import ideje a DB-kapcsolatot, a schema- és tartalomellenőrzést, a beszúrást
és commitot tartalmazza; az előzetes fájlbeolvasást és Python-adatvalidálást nem.
A pontos keresés ideje a repository kapcsolódását és sémavizsgálatát is tartalmazza.
A második loader mérésében zárvárakozás is van. Ezek egyetlen fejlesztői futás
adatai, nem átlag/p95 statisztikák.

Bizonyítékok:

- [JUnit tesztjelentés](../evaluation/clean_inventory/test_results.xml)
- [Valódi DB-verifikáció, rollback, dokumentumpróbák](../evaluation/clean_inventory/postgres_verification.json)
- [Offline kimenetek](../evaluation/clean_inventory/matching_offline.json)
- [PostgreSQL-kimenetek](../evaluation/clean_inventory/matching_postgres.json)
- [10 000 sor és konkurens seed](../evaluation/clean_inventory/scalability.json)

A `scripts.verify_clean_inventory_report` sikeresen ellenőrizte a datasetet,
mind a 32 dokumentumot és mind a négy mérési riport aktuális kódlenyomatát.

## G. Integráció

- `config/schema.json`: pontosan ugyanaz a 11 mező, automatizált PG-összevetéssel.
- `InventoryRepository`: UNIQUE felismerés, célzott inventory lookup, fuzzy fallback.
- `reconcile_document`: a meglévő ProcessingResult/PreparedDocument szerződés,
  valódi validáció, rangsor, mezőeltérések és review-javaslatok.
- Azonos nevű két eszköz külön leltári számhoz és külön rekordhivatkozáshoz kötődik.
- Location eltérésnél az azonosság megmarad, külön UPDATE-javaslat készül.
- SQL: tényleges executor + új séma/adatok, a nyelvi SQL/answer válasz helyettesített.
- Streamlit: a főoldal és az egyeztetési panel AppTesttel indult és működött.
- RAG/HYBRID: meglévő tesztek és irányítási smoke, külső szolgáltatások
  tesztválaszaival. A Qdrant tartalma és szinkronizációs állapota nem változott.

## H. Biztonság

Az író eszközök célja kódban rögzített, env-fájllal nem írható át `inventory`-ra.
A CLI a shellbeli eltérést is leállítja. A tényleges current_database() külön
ellenőrzött. Az új SQL a célnevet önállóan is védi.

A teljes import egy tranzakció, a batchértékek paraméterezettek, a táblát
konkurens írókkal szemben zároljuk. Nincs DROP, DELETE, TRUNCATE, upsert,
régi adatmásolás vagy azonosító-javítás. Az eltérő tartalom kézi beavatkozást igényel.
A migráció és import külön explicit kapcsolóval engedélyezhető, nincs automatikus
app-indítási seed. A verifier ténylegesen csak olvasó tranzakció.

Az adatbázisos tesztek külön `initdb` klasztereken futottak, az alkalmazás
kapcsolati adatait nem használták. Az izolált klaszterben létrehozott régi-adatbázis
őrtábla változatlan maradt. A valódi felhasználói adatbázist ebben a feladatban
nem módosítottuk és nem használtuk a tesztekhez. A `.env` fájl változatlan maradt.

## I. Felhasználói teendők

A teljes, parancsokkal egyező [10 lépéses Windows/pgAdmin útmutató](clean_inventory_database.md):
új DB → schema/CHECK/UNIQUE → generálás → dry-run/import → verifier → külön
olvasószerep és kézi `.env` átállítás → Streamlit → L-00001 keresés → D01/D02
feltöltés → eredményellenőrzés.

A helyi adatbázis-módosítás előfeltétele az `inventory_ai_clean` cél kifejezett
jóváhagyása. A most elkészült eszközök és SQL-fájlok a végrehajtás előtt átnézhetők.

## J. Hiányosságok és Definition of Done

Fennmaradó külső lépések: helyi telepítés/jogosultság és kézi konfigurációváltás;
élő OpenAI-val végzett kinyerési minőségmérés; Qdrant-szinkron külön fejlesztésként.
Két ismert matcher-kategóriaeltérés dokumentált, változatlan algoritmus mellett.
Az adatbázis-előkészítő/generáló/importáló/verifikáló funkciókban nincs befejezetlen TODO.

| Előírt teljesítési feltétel | Állapot és bizonyíték |
|---|---|
| Új tesztadatbázis létrehozását támogató SQL | Kész; izolált PG-n alkalmazva |
| 11 mezős tábla | Kész; tényleges schema.json-egyezés tesztelt |
| inventory_number UNIQUE és NOT NULL | Kész; hibás rekordmódosítások elutasításával tesztelt |
| quantity=1 adatbázisban | Kész; quantity 2/NULL elutasítása tesztelt |
| Megfelelő adatminőségi megszorítások | Kész; 9 CHECK + NOT NULL + UNIQUE |
| Régi adatbázis érintetlen | Tesztek izoláltak; valódi üzleti DB-n nincs írás |
| Generátor elkészült | Kész; unit és 10k próba |
| Hivatalos készlet 1000 rekord | Kész; CSV/JSON és PG-verifier |
| Minden leltári szám egyedi | Kész; 1000/1000 |
| Konzisztens eszközkatalógus | Kész; 26 modell, tíz kategória |
| Ismétlődő típusok/cikkszámok | Kész; mind a 26 típus ismétlődik |
| Reprodukálható adatok | Kész; több seed, ismétlés, kanonikus hash |
| Kanonikus CSV/JSON | Kész; egyezőség tesztelt |
| Dataset manifest | Kész; adat/séma/dokumentum hash |
| Biztonságos importer | Kész; explicit célvédelem |
| Adatbázisnév ellenőrzött | Kész; konfiguráció és tényleges kapcsolat |
| Tranzakciós betöltés | Kész; batch utáni hiba visszagörgetve |
| Biztonságos újrafuttatás | Kész; soros és konkurens próba |
| Rollback hiba esetén | Kész; 250 sor után megszakítva 0 tartós sor |
| Nincs automatikus adatvesztés | Kész; eltérő nem üres táblát elutasít |
| DB-verifier | Kész; read-only, teljes hash/séma/minőség |
| Unit tesztek | Kész; teljes csomagban sikeres |
| Integrációs tesztek | Kész; valódi izolált PG és Docling |
| Meglévő tesztek nem sérültek | Kész; mind a korábbi 202 sikeres |
| Rekordegyeztetés kompatibilis | Kész; 16 eset, két őszintén jelzett kategóriaeltéréssel |
| Dokumentumok és ground truth | Kész; 32 fájl, 16 független referencia |
| DB-dokumentáció | Kész; clean_inventory_database.md |
| Generátordokumentáció | Kész; synthetic_inventory_dataset.md |
| Reprodukálási útmutató | Kész; clean_inventory_testing.md |
| README frissítve | Kész |
| PROJECT_MAP frissítve | Kész |
| pgAdmin 4 útmutató | Kész; tíz lépés és PowerShell-alternatívák |
| Felhasználó saját clean DB-jének telepítése | Külön művelet, nem alkalmazva |

Az implementációs Definition of Done teljesült. A helyi telepítést és az élő
AI-minőséget az izolált teszteredmények nem helyettesítik.
