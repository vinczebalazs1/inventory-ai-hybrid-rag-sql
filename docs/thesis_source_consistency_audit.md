# InventoryAI – forráskód és mérési riportok konzisztenciaauditja

**Ellenőrzés:** 2026-11-07, Europe/Budapest.  
**Repository:** `C:\Users\vincz\Desktop\inventory-ai`.  
**Branch:** `main`. **HEAD:** `a7bd4278aaa4a7da6aa7375ff1741c6e9107ab83`.

## Összefoglaló döntés

**A korábbi 84/84 és 69/84 eredmény összeegyeztethető.** A jelenlegi munkakönyvtár mind a 84 fájlja bájtpontosan megfelel a két clean mérési riport manifestjének. Ugyanezen fájlok HEAD-ben tárolt változatai közül 69 egyezik nyers SHA-256 szerint; a fennmaradó 15 **kizárólag LF/CRLF sorvégben tér el**. LF-re normalizálva mind a 84 fájl teljes bájttartalma azonos.

A `repository.py` és a `candidate_service.py` is ebbe a körbe tartozik: csak az utolsó sor CRLF/LF végződése különbözik. A kód, SQL-feltételek, kandidánsválogatás és Python AST nem változott e két összehasonlított példány között.

**A meglévő precision-, recall-, F1-, 14/16 referenciaegyezési és történeti futásidő-eredmények felhasználhatók a jelenlegi implementációhoz, a mérési hatókör és dátum feltüntetésével. Releváns kódváltozás miatt szükséges újramérést nem azonosítottam.** A 311 sikeres teszt régi JUnit-eredménye valós, ellenőrizhető fájlállítás; annak teljes futását viszont az XML nem köti közvetlenül forrásmanifesthez vagy commithoz. Ha a dolgozat kifejezetten a jelenlegi commit teljes tesztfutását kívánja igazolni, ehhez további futási bizonyíték vagy új, verzióhoz kötött JUnit szükséges.

A korábban vizsgált konkrét ZIP nem állt rendelkezésre az auditban. A 69/84 eredményt a HEAD Git-objektumain és egy **memóriában elkészített, LF-beállítású Git ZIP-exporton** reprodukáltam. Ez igazolja a sorvégkülönbség magyarázatát ebben a repositoryban; az ismeretlen ZIP összes tartalmának azonosságát nem bizonyítja.

## 1. Git-verzió, munkakönyvtár és vizsgálati módszer

### 1.1. Kiinduló állapot

| Elem | Ellenőrzött eredmény |
|---|---|
| Aktív branch | `main`, követett referencia: `origin/main` |
| HEAD teljes SHA | `a7bd4278aaa4a7da6aa7375ff1741c6e9107ab83` |
| HEAD commit dátuma | 2026-10-25T10:53:45+01:00, a Git által tárolt időzónával |
| HEAD üzenete | `feat(database): add production-ready synthetic inventory dataset and PostgreSQL setup` – commitcím, nem az audit minősítése |
| Módosított követett fájl | Nincs; unstaged és staged diff is üres |
| Már az audit előtt nem követett fájl | `docs/thesis_technical_handover.md` |
| Az audit egyetlen új fájlja | `docs/thesis_source_consistency_audit.md` |
| Remote ellenőrzés | Nem történt fetch; az állítás a helyi repositoryra vonatkozik |

A korábbi átadás „tiszta munkakönyvtár” állítása a 2026-10-25-i feladat **kezdetére** vonatkozott. Most annak elkészült, nem követett Markdown-fájlja már jelen volt; ez nem forráskód-eltérés.

Ellenőrző Git-parancsok:

```powershell
git --no-optional-locks -c core.fsmonitor=false status --short --branch --untracked-files=all
git branch --show-current
git rev-parse HEAD
git --no-optional-locks -c core.fsmonitor=false diff --quiet
git --no-optional-locks -c core.fsmonitor=false diff --cached --quiet
git log --date=iso-strict --format="%H %ad %s" -8
```

A `--no-optional-locks` és `-c core.fsmonitor=false` csak e parancsok végrehajtását érinti; repository-konfigurációt nem írtam át.

### 1.2. Ellenőrzési módszer

1. Közvetlenül beolvastam a kért JSON-riportokat és a JUnit XML-t.
2. A riportban ténylegesen felsorolt fájlokon `SHA256(Path(path).read_bytes())` ellenőrzés történt. Nem egy mai, eltérő fájllistát tekintettem automatikusan a régi mérés manifestjének.
3. Újraszámítottam a manifest aggregált hash-ét a meglévő kód képletével: `SHA256(json.dumps(manifest, sort_keys=True).encode())`.
4. A HEAD nyers Git-objektumait `git cat-file --batch` segítségével olvastam. Ezeket külön kezeltem a munkakönyvtári bájtoktól.
5. Eltérésnél kizárólag a `b"\r\n" → b"\n"` transzformációval hasonlítottam össze a teljes tartalmat. Nem távolítottam el szóközöket, kommenteket, üres sorokat vagy BOM-ot.
6. Az eltérő 12 Python-fájl AST-jét is összevetettem `utf-8-sig` dekódolás és `ast.dump(ast.parse(...))` alapján. Mind egyezett.
7. Git history alapján ellenőriztem a régi 63 fájlos forráshalmazt az `0179ade...` és a jelenlegi HEAD között.
8. A meglévő `read_bundle` és `read_ground_truth` segítségével ellenőriztem a clean készlet, a ground truth és a dokumentumok fájlintegritását. A generátor összehasonlítása memóriában történt.
9. A mentett metrikákat olvastam ki; **ebben az auditban nem futott új matchingbenchmark, pytest-tesztfutás, élő LLM-kérés vagy adatbázis-művelet**.

A forráskódot, teszteket, konfigurációkat, adatokat és meglévő riportokat nem módosítottam. A korábbi technikai átadást sem írtam át.

### 1.3. Mit bizonyít a hash?

A fájlonkénti SHA-256 az adott bájttartalom egyezését bizonyítja a riportban rögzített lenyomattal. Egy commit és egy munkakönyvtár azonos értelmű szövegfájljainak nyers hash-e eltérhet a sorvégkezelés miatt. A vizsgálat ezért külön közli a **bájtpontos egyezést**, a **kizárólag sorvégben eltérő tartalmat**, valamint a **futási eredmény eredetének bizonyítékát**.

A riportok saját manifestje nem terjed ki automatikusan minden függőségre, tesztre vagy futtatási körülményre. Az „IGAZOLT” státusz az alább pontosított forráskapcsolatra és mérési hatókörre vonatkozik, nem egy mai teljes újrafuttatásra.

## 2. A 84 fájlos manifest ellenőrzése

### 2.1. Összesítés

A `evaluation/clean_inventory/matching_offline.json` és `matching_postgres.json` **azonos, 84 bejegyzéses** `source_manifest` értéket tartalmaz. Mindkét riport aggregált hash-e belsőleg helyes.

| Összehasonlítás | Nyers hash egyezik | Eltér | Hiányzik | Kizárólag sorvégeltérés | Egyéb formázás / tartalmi változás |
|---|---:|---:|---:|---:|---:|
| Manifest ↔ jelenlegi munkakönyvtár | **84** | **0** | 0 | 0 | 0 |
| Manifest ↔ HEAD nyers Git-objektumok | **69** | **15** | 0 | **15** | **0** |
| Munkakönyvtár ↔ HEAD, CRLF→LF után | **84 teljes tartalmi egyezés** | 0 | 0 | – | 0 |
| Manifest ↔ LF-beállítású HEAD ZIP-export | **69** | **15** | 0 | **15** | **0** |

A clean aggregált forráshash a két riportban és a jelenlegi munkakönyvtárban:

```text
184c273f346a4e9adda1019ef719c156e3c827a5116481af428d66e14c470036
```

Forrás: `app/test_data/artifacts.py::source_hashes`, 19–25. A 84 fájl köre: `app/**/*.py`, közvetlen `scripts/*.py`, `config/*`, rekurzív `migrations/**/*.sql`, továbbá `requirements.txt` és `requirements-dev.txt`.

**Nem része ennek a manifestnek:** tesztforrások, `app/prompts/*.txt`, teljes telepített csomaglista, a JUnit fájl és valamennyi futási környezeti paraméter. Az offline matching nem használ dokumentum-LLM-promptot; a teljes 311 tesztes futás igazolásánál viszont a teszt- és környezeti lefedettség hiánya lényeges.

### 2.2. A 15 eltérés és pontos oka

A következő táblázat a **HEAD/manifest eltéréseket** sorolja fel. A munkakönyvtár ezeknél is bájtpontosan megfelel a manifestnek. A teljes várt/munkakönyvtári hash az A. mellékletben szerepel.

Minden sorban: HEAD-ben csak LF sorvégek; CRLF→LF után a két fájl bájtpontosan azonos. Nincs más formázási, BOM-, kódolási vagy tartalmi eltérés.

| Fájl | Munkakönyvtári CRLF / önálló LF darab | HEAD SHA-256 |
|---|---:|---|
| `app/rag/embedding/embedding_service.py` | 2 / 53 | `9a77c348f419d701078db8a6ce49cd29a87111393b3ae280024a4ee95a5ceda2` |
| `app/rag/ingestion/chunker.py` | 41 / 78 | `3996aee7ab232eb22414ab9d4a99019c118de65fe9512ba72a061d323833e752` |
| `app/rag/ingestion/parser.py` | 71 / 38 | `d82b0a13b38604073166e14a7141a911f1a8e30268fc4c3109a5f0f0b40cc7ad` |
| `app/rag/models/rag_models.py` | 2 / 17 | `59b32b3233569d8ba649064d3c5a219ca1efa3b784ed08a7972b8812142aff17` |
| `app/rag/retrieval/retriever.py` | 23 / 34 | `5919b66e01e6200c5fb0bb6682ec441bee0e7c33124e40de12c670dbcc447592` |
| `app/rag/vector_store/qdrant_client.py` | 16 / 73 | `a8f1b120561bc9d8b12787ca0b6cfe823ca593d45afb5018f63de2cbb82e10aa` |
| `app/record_matching/candidate_service.py` | 1 / 56 | `aa2a22be0bb35d20672ee19d3ea9ec745a328e60d0966082a04f1c8e3638d8da` |
| `app/record_matching/repository.py` | 1 / 428 | `9f11c97c7938e585eeb99847ddaab9e2fce1c5e5dbae7741701987aa1a22ec4e` |
| `app/services/schema_service.py` | 10 / 56 | `bcd6c7cc12a6cf3df955c828ed0bed9351a81f691cfcee9b68a949b0c8bacdfd` |
| `app/services/sql_generation_service.py` | 1 / 42 | `7e2bdb7d26cf43d9f4803e24b9847518820cf56b9a37f022645e3c4b94651d7f` |
| `scripts/audit_matching_schema.py` | 1 / 26 | `9151043b576146eff5b9d41666dbabaa6bc7115e00e5c68a37c17a60963b51d5` |
| `scripts/extract_schema.py` | 63 / 0 | `bb9faaff08e7032e11e282f7a8c089c25b47e42d1d0f07184e11584feaa396e5` |
| `config/schema.json` | 47 / 0 | `6cca1c4402ce476d7a8bde4030cfb3ad4865ca56969f15ebfa4f28c13d9873b8` |
| `config/schema_descriptions.yaml` | 14 / 0 | `b844e66991efaf00d6f503c9b3d7c1d0977860859c272d088337854cdae92aec` |
| `requirements.txt` | 27 / 0 | `bef65ce54d0006a3aef3dd7106aa4dd8752265ae2ccaa09abf73e36085b7303a` |

**Külön ellenőrzött kritikus fájlok:**

- `app/record_matching/repository.py`: a **429. sor** végződése CRLF a munkakönyvtárban, LF a HEAD-ben; a többi 428 sor LF. A manifest/munkakönyvtár hash: `56d0a2bfa40facffa5a57ae7e4fd76580172326ad5ba611add0b1c85bfe83b1d`.
- `app/record_matching/candidate_service.py`: az **57. sor** végződése CRLF a munkakönyvtárban, LF a HEAD-ben; a többi 56 sor LF. A manifest/munkakönyvtár hash: `c889ebd03dd7c77191453b5fcb3be6d3e6d8f4bc36eff14b67a1dad3115232e6`.
- Mindkét fájl elején UTF-8 BOM van **mindkét** példányban; a BOM nem az eltérés oka.
- Mindkét Python AST azonos. Az összehasonlított változatokban nincs különbség a keresési feltételekben, a leltáriszám-prioritásban, a fuzzy jelöltek kiválasztásában vagy a limitkezelésben.

### 2.3. Miért látszik tisztának a Git a sorvégeltérések ellenére?

A helyi Git-konfigurációban `core.autocrlf=true` szerepel. A vizsgált Python/config/requirements fájlokra a `git check-attr text eol` eredménye `unspecified`. A `.gitattributes` csak a szintetikus JSON/CSV LF-sorvégeit és a PDF/DOCX bináris kezelését rögzíti.

A `git ls-files --eol` például ezt mutatja:

```text
i/lf    w/mixed    app/rag/embedding/embedding_service.py
i/lf    w/mixed    app/record_matching/candidate_service.py
i/lf    w/mixed    app/record_matching/repository.py
i/lf    w/crlf     config/schema.json
i/lf    w/crlf     requirements.txt
```

A Git indexelt szövege és a munkakönyvtári bájtok ezért nem ugyanazt a nyers hash-t adják. Ez önmagában nem commitolatlan logikai változás. A mérések a munkakönyvtár nyers bájtjait hash-elték; az LF-tartalmat őrző export azokkal nem minden fájlon egyezik bájtpontosan.

### 2.4. ZIP-ellenőrzés: mit sikerült és mit nem sikerült reprodukálni?

A repositoryban csak `app/document_processing.zip` található ZIP-ként; ez nem teljes, 84 fájlos projekt-export. A felhasználó által említett korábbi teljes ZIP pontos fájlja és hash-e nem volt megadva.

A jelenlegi HEAD-ből a következő parancs kimenetét **memóriában**, fájlkiírás/kicsomagolás nélkül vizsgáltam:

```powershell
git -c core.autocrlf=false -c core.eol=lf archive --format=zip HEAD
```

Eredménye: **69 bájtpontos + ugyanaz a 15 kizárólag sorvégben eltérő fájl**. A memóriabeli ZIP SHA-256 értéke: `cfcfa9e22ae58dadd6b231ddbd0f6193234de1f72f35d37941983b265fde91c1`.

Kontrollként a sima `git archive --format=zip HEAD` a jelenlegi `core.autocrlf=true` beállítással **5/84** nyers egyezést adott; mind a további 79 eltérés szintén csak sorvég. Ez azt is mutatja, hogy nem helyes minden ZIP-készítési módra automatikusan 69/84 egyezést várni. Az exportbeállításokat is rögzíteni kell.

**Következtetés:** a 69/84 és a 84/84 eredményhez nem szükséges kódváltozás vagy hibás korábbi ellenőrzés feltételezése. Az adott régi ZIP azonossága továbbra is csak a konkrét fájl vizsgálatával állapítható meg.

## 3. Git history és a mért verzió óta történt változások

### 3.1. Azonosítható történeti pontok

| Commit | Dátum a Gitben | Kapcsolat |
|---|---|---|
| `ea6f68419fdf815cbf592c8c2d2f35a28d306595` | 2026-10-13 | Korábbi record matching modul és riporttörténet |
| `0179ade7c66f9d6ebe0a6212515e2db7a01a56a9` | 2026-10-17T12:12:36+02:00 | Leltáriszám-alapú azonosítás és a 2026-10-17-i mérési állapot |
| `a7bd4278aaa4a7da6aa7375ff1741c6e9107ab83` | 2026-10-25T10:53:45+01:00 | Clean tesztadat-infrastruktúra és clean riportok commitja; jelenlegi HEAD |

A clean riportok 2026-10-18-i futásidőt rögzítenek, a commitjuk későbbi. Nem állítom, hogy a mérés közben már az október 25-i commit volt checkoutolva. A bizonyíték az, hogy **a mérésben rögzített fájltartalom megfelel a ma vizsgált implementációnak**.

### 3.2. A régi matchingmérés 63 fájlja

A `matching_metrics.json` eredeti manifestje **63 fájlos**, nem 84. Az eredeti lista mind a 63 fájlja bájtpontosan egyezik a jelenlegi munkakönyvtárban, és a lista aggregált hash-e ugyanaz:

```text
5b4b1c6b90a14ed427bfe26d3457bacc72bcb662d9ff7cba4c96a8ab8cda785b
```

A 63 fájl Git-objektumai az `0179ade...` és `a7bd427...` commitok között is **63/63 bájtpontos egyezést** mutatnak. A mért forráskörben nincs utólagos logikai változás.

A mai `app/evaluation/runner.py::implementation_hashes` már **79 fájlt** talál. Az eredeti 63-hoz 16 új fájl csatlakozott; nincs eltűnt vagy módosult régi bejegyzés. Emiatt a teljes mai aggregált hash:

```text
4749591a954aeccfb783c23872c3cbcca2ac6641f90a9aabace4b3ba4f92758a
```

A 16 hozzáadott fájl:

- `app/test_data/__init__.py`
- `app/test_data/artifacts.py`
- `app/test_data/catalog.py`
- `app/test_data/cli.py`
- `app/test_data/database.py`
- `app/test_data/documents.py`
- `app/test_data/evaluation.py`
- `app/test_data/generator.py`
- `app/test_data/models.py`
- `app/test_data/validation.py`
- `scripts/evaluate_clean_inventory.py`
- `scripts/generate_inventory_data.py`
- `scripts/load_inventory_data.py`
- `scripts/prepare_inventory_database.py`
- `scripts/verify_clean_inventory_report.py`
- `scripts/verify_inventory_data.py`

A meglévő `scripts/verify_matching_report.py` a **mai teljes fájllistát** és aggregált hash-t követeli meg, ezért stale állapotot jelezne. Ez az ellenőrző jelen esetben a forráshalmaz bővülését és a régi fájl tartalmi megváltozását nem választja szét. Az audit fájlonkénti vizsgálata alapján a régi matchingmérés érvényességét a 16 kiegészítő fájl nem cáfolja.

A 79 és 84 különbségét a clean hashfüggvény bővebb köre okozza: 3 rekurzívan bevont clean SQL-migráció és a két requirements fájl. A két aggregált hash nem ugyanannak a fájlhalmaznak a hash-e.

### 3.3. A tesztkörnyezet tényleges bővülése

A Git diff szerint négy új tesztfájl került be: `test_inventory_clean_integration.py`, `test_inventory_data_generator.py`, `test_inventory_scalability.py`, `test_inventory_seed_loader.py`. A `requirements-dev.txt` módosult. Ezek az új clean infrastruktúrához kapcsolódnak; a régi, mért 63 fájlos algoritmusforrást nem írják át.

A régi riportban rögzített Python/függőségverziókat a jelenlegi telepítéssel összevetettem: Python **3.11.9**, RapidFuzz **3.14.6**, Pydantic **2.12.5**, psycopg2-binary **2.9.11** egyezik. A jelenleg telepített pytest 8.4.2, Docling 2.80.0, OpenAI SDK 2.29.0; a JUnit nem rögzít teljes csomaglistát. Nem állítható ebből, hogy minden transzitív függőség és rendszerparaméter azonos az egykori futáséval.

## 4. A mérési riportok ellenőrzöttségi státusza

### 4.1. Riportonkénti döntés

| Riport | Rögzített dátum / forráskapcsolat | Státusz | Felhasználhatóság |
|---|---|---|---|
| `evaluation/results/matching_metrics.json` | 2026-10-17T10:04:03.494402+00:00; 63 fájlos manifest + fixture hash + Python/könyvtárverziók | **IGAZOLT** az eredeti mérési forráskörre | Precision, recall, F1 és kapcsolódó determinisztikus metrikák a jelenlegi, változatlan matchingimplementációhoz kapcsolhatók. Idők történeti offline részidők. |
| `evaluation/clean_inventory/matching_offline.json` | 2026-10-18T14:10:34.970306+00:00; 84 fájlos manifest + kanonikus adathash | **IGAZOLT** | 84/84 raw egyezés; 14/16 a rögzített struktúrált inputokkal, LLM nélkül. |
| `evaluation/clean_inventory/matching_postgres.json` | 2026-10-18T14:11:11.898525+00:00; ugyanaz a 84 fájl és adathash; mode=isolated_postgres | **IGAZOLT** a mentett izolált PG-mérés forráskapcsolata | A 14/16 a jelenlegi matchingkódhoz kapcsolható. Nem friss élő DB-ellenőrzés vagy éles latencygarancia. |
| `evaluation/results/inventory_search_benchmark.json` | 2026-10-17T10:03:32.422812+00:00; implementációhash + külön benchmarkforrás-hash | **IGAZOLT**, a lent leírt kapcsolaton keresztül | A 4000 soros, query-stage-only időmérés a változatlan kódhoz és benchmarkhoz kötött; történeti mérésként idézhető. |
| `evaluation/clean_inventory/test_results.xml` | 2026-10-18T16:10:36.938069+02:00; 311 testcase, 0 failure/error/skipped; nincs commit/manifest property | **NEM ELDÖNTHETŐ** a teljes futás közvetlen, pontos forrásverzió-kötése | A 311 sikeres történeti teszt ténye igazolt a fájlból; „a jelenlegi commiton most igazolt teljes suite” nem állítható. |

**ÚJRAMÉRÉS SZÜKSÉGES releváns kódváltozás miatt:** a vizsgált bizonyítékok alapján **egyik fenti algoritmikus mérésnél sem**. A JUnit bizonyítási hiánya nem azonos bizonyított kódváltozással; azt külön kell kezelni.

### 4.2. Precision, recall és F1

A `matching_metrics.json` 74 esetből 10 calibration és 64 test esetet különít el, 5 ismétléssel. A test csoportban 62 identity-evaluable eset és 47 létező referenciarekordos eset van.

| Test csoport metrikája | Exact-only | Hybrid |
|---|---:|---:|
| TP / FP / FN | 25 / 0 / 22 | 31 / 0 / 16 |
| Precision | 1.000000 | 1.000000 |
| Recall | 0.531915 | 0.659574 |
| F1 | 0.694444 | 0.794872 |
| Top-1 accuracy | 0.638298 | 0.808511 |
| Review rate | 0.796875 | 0.796875 |

Ezek **a meglévő riportból kiolvasott**, nem ebben az auditban újramért értékek. A forrás- és fixture-egyezés miatt nincs jelenlegi tartalmi ok az elvetésükre. A `tests/fixtures/matching_evaluation.json` aktuális SHA-256 értéke megfelel a riportnak:

```text
773aaf4da61ec1bafc1f86619e566b004546eb6895795664f7729d500b58d062
```

A mérés hatóköre: ismert strukturált mezők, fixturealapú retrieval és valódi matching/diff/javaslati kód. Nem élő LLM-mezőkinyerési vagy Qdrant-keresési pontosság. A nulla mért FP nem általános hibamentességi garancia.

### 4.3. A clean 14/16 referenciaegyezés

A két clean riportban ugyanaz az eredmény: **14 megfelelt, 2 eltért**. D05 és D06 esetén kizárólag a `match_category` ellenőrzés hamis; az identity, field_differences, actions és review ellenőrzések igazak.

| Eset | Elvárt státusz | Mentett tényleges státusz | Értelmezés |
|---|---|---|---|
| D05 | AMBIGUOUS_MATCH | SEARCH_INCOMPLETE | A releváns jelöltek korlátozása miatt a keresés nem teljes; nincs hibás rekordkiválasztás. |
| D06 | CONFLICTING_DATA | SEARCH_INCOMPLETE | A hiányos keresés státusza megelőzi a jelöltből származó konfliktus végső besorolását; az item_code eltérés látható. |

A kanonikus 1000 rekordos készlet hash-e mindkét riporthoz illeszkedik:

```text
3a990307ca2e38916cfad1eb3410b3da7609bedcc98e3f43d0717903cdb4982a
```

A `read_bundle` ellenőrizte a fájlhash-eket, CSV/JSON egyezést, sémát, minőségi szabályokat és seed szerinti memóriabeli újragenerálást. A `read_ground_truth` a ground truth és dokumentumfájlok integritását is ellenőrizte. A ground truth fájl aktuális hash-e: `0102dff4acb9d6417969611de737c513b4199a795c9c5d393ce41b04566e5413`.

A 14/16 nem a 32 PDF/DOCX fájl élő LLM-es feldolgozásának sikeraránya. A clean értékelő `app/test_data/evaluation.py::processing_input` ismert mezőket ad a valódi normalizáló/egyeztető logikának. A PostgreSQL-változat tényleges izolált adatbázison keresett, de az extraction/mapping inputja ott is ismert.

### 4.4. Futásidők és a benchmark bizonyítási lánca

Az `inventory_search_benchmark.json` nem tartalmaz saját teljes manifestet. Viszont az `implementation_sha256` értéke azonos a `matching_metrics.json` ellenőrzött, 63 fájlos manifestjének aggregált hash-ével. Ezt egészíti ki a mérőkód külön hash-e:

```text
tests/test_matching_postgres.py
a4949bb37d81d04a6d6738d005f170dc6f0a4b527d5ba3559c8926880cf43479
```

Ez az érték egyezik a `benchmark_source_sha256` mezővel, a jelenlegi munkakönyvtárral és a HEAD Git-objektummal is. A benchmark tényleges kódja: `tests/test_matching_postgres.py::test_isolated_inventory_search_benchmark`, 302–356.

| Mentett mérés | Átlag | p95 | Hatókör |
|---|---:|---:|---|
| Offline exact-only, test csoport | 0.639051 ms | 1.016200 ms | Fixture retrieval + reconciliation; nincs valódi PG/LLM latency. |
| Offline hybrid, test csoport | 1.097718 ms | 1.318900 ms | Ugyanaz a kör; 320 időminta/stratégia. |
| Régi OR feltételes PG lookup | 2.410736 ms | 2.675700 ms | 4000 sor; 5 warmup + 50 mérés; már megnyitott kapcsolat/snapshot. |
| Célzott inventory lookup | 0.577654 ms | 0.688700 ms | Ugyanabban a benchmarkban; 1 materializált sor. |
| Fuzzy fallback | 37.998464 ms | 40.838400 ms | Ugyanott; incomplete scope, 1003 materializált sor. |

A clean offline riport teljes értékelési ideje **249.849500 ms**, a clean izolált PostgreSQL-riporté **1113.577400 ms**. Ezek az `evaluate` teljes 16 esetes futásának riportolt idejei, nem egy dokumentum idői; a kód a forráshash-képzést is az időablakon belül végzi. A két értéket nem szabad teljes Docling→LLM→DB feldolgozási időnek nevezni.

A forráskapcsolat igazolt, de a történeti számokból nem állítható, hogy a mai hardveren, aktuális terhelés és DB-állapot mellett pontosan ugyanennyi idő lesz. Teljesítménygarancia vagy mai környezetre vonatkozó idősor megfogalmazásához új környezetazonos mérés kellene; pusztán a feltárt sorvégeltérések miatt nem kell elvetni a meglévő időméréseket.

### 4.5. A 311 tesztes JUnit bizonyítékának határa

Az XML-ben ténylegesen 311 `testcase` elem van, és nincs `failure`, `error` vagy `skipped` elem. A suite attribútumai ugyanezt rögzítik. Futásidő: **134.790 s**. A fájl SHA-256 értéke:

```text
b4f924371cca5e3c93f1eb2c369ccfe476f5cc4fab54f8cc4f51e9dde9dac3fe
```

**Közvetett összefüggés:** az XML és a clean riportok ugyanabban a HEAD commitban vannak; a JSON-ok dátumai a JUnit futásának időablakához illeszkednek. Az integrációs teszt kódja valóban készít `matching_postgres.json` és `postgres_verification.json` fájlokat. A clean JSON-ok aktuális forráskapcsolata igazolt.

**Hiányzó közvetlen kötés:** az XML-ben nincs `properties` vagy `property`, commit SHA, source manifest, tesztforráshash vagy a kapcsolódó JSON-riportok hash-e. A clean 84 fájlos manifest a tesztforrásokat nem tartalmazza. Így az összes 311 testcase egykori pontos tesztforrása és futási konfigurációja nem rekonstruálható kizárólag ebből a bizonyítási láncból.

Ezért megfelelő megfogalmazás: **„A 2026. október 18-i mentett JUnit-riport 311 sikeres tesztet, nulla hibát és nulla kihagyást rögzít.”** Erősebb állításként nem használható: „A jelenlegi HEAD-en most újrafuttatott, hash-sel hozzákapcsolt 311 teszt sikeres.”

## 5. Hatás a szakdolgozat 5.2 fejezetére

A jelenlegi dolgozatszöveg nem része ennek az auditnak; az alábbiak a feladatban megnevezett állításokra vonatkoznak.

| Állítás | Használható? | Szükséges pontosítás |
|---|---|---|
| Exact-only/hybrid precision, recall, F1 | **Igen – IGAZOLT** | A 64 tesztesetre, a rögzített fixture-re és a 2026-10-17-i mérésre kell hivatkozni; a kód releváns forrásköre változatlan. |
| Clean offline/PG 14/16 | **Igen – IGAZOLT** | D05/D06 kategóriaeltérését és az ismert strukturált bemenetet is közölni kell. |
| PG-keresési sebesség javulása | **Igen, a mért körben** | 4000 sor, 50 ismétlés, query-stage-only; connection és sémaaudit nélkül. Nem teljes alkalmazássebesség. |
| Teljes offline reconciliation idők | **Igen, történeti adatként** | Fixture-keresés; nem PostgreSQL/LLM vagy teljes dokumentumfeldolgozás ideje. |
| 311 sikeres automatizált teszt | **Igen, dátumozott korábbi JUnit-eredményként** | A jelenlegi commit pontos teljes futásához való közvetlen kötés NEM ELDÖNTHETŐ. |
| A ZIP 15 eltérése algoritmusváltozás | **Nem igazolt; a HEAD-re cáfolt** | A HEAD-vizsgálatban mind a 15 csak sorvégeltérés. Az eredeti ZIP külön fájlvizsgálatot igényel. |
| A jelenlegi teljes projekt aggregált hash-e azonos a régi 63 fájlos hash-sel | **Nem** | A forráshalmaz 16 fájllal bővült; az eredeti 63 fájl viszont változatlan. |
| A mérés idején már a mai HEAD commiton futott a rendszer | **Nem bizonyított** | A riportok futásdátuma és későbbi commitolása különböző; tartalmi hozzárendelést szabad állítani. |

Az 5.2-höz használható rövid auditmegállapítás:

> A mérési riportokban rögzített forrásmanifesteket fájlonként összevetettük az elemzett implementációval. A clean riportok 84 fájlja a munkakönyvtárban bájtpontosan egyezik. A Gitben tárolt változatok 15 nyers hash-eltérése kizárólag sorvégformátumból adódik. A korábbi matchingmérés 63 fájlos eredeti forrásköre változatlan; a mai aggregált hash eltérését a később hozzáadott tesztadat-infrastruktúra okozza. A 311 sikeres tesztet tartalmazó JUnit-riportot dátumozott történeti bizonyítékként kezeljük, mert az XML nem rögzít közvetlen forrásverzió-azonosítót.

Ez nem módosítja a precision/recall/F1 vagy 14/16 értékeket. A mérési módszert és a hivatkozás pontosságát egészíti ki.

## 6. Minimálisan szükséges következő teendők

### 6.1. A jelenlegi eredmények felhasználásához

1. A dolgozatban rögzíteni kell az auditált HEAD-et, a mérési dátumokat és a manifest hatókörét.
2. A 69/84 eltérést sorvégkülönbségként kell leírni a vizsgált HEAD/LF-export esetében. A korábbi konkrét ZIP teljes azonosságát csak annak átvétele után lehet kijelenteni.
3. A 311-es tesztszámot a 2026-10-18-i JUnit-ra kell korlátozni. Ha ez elegendő a dolgozat állításához, **nincs kötelező teljes újrafuttatás**.
4. A régi riportokat, hash-eket és manifesteket meg kell őrizni. A nyers eltéréseket nem szükséges a források vagy a riportok átírásával eltüntetni.
5. Algoritmikus újraméréshez jelenleg nincs kódváltozásból eredő ok.

### 6.2. Ha közvetlenül a mai commitra kötött teljes JUnit szükséges

Elsőként egy már létező CI-/futtatási napló pótolhatná a hiányzó commit-, tesztmanifest- és környezeti kapcsolatot. Ha nincs ilyen, új teljes tesztfutás indokolt. Ez **bizonyítékpótlás**, nem a feltárt sorvégkülönbségek miatti algoritmikus újramérés.

Függőségek: a `requirements-dev.txt` teljes környezete; PostgreSQL `initdb` és `pg_ctl` (a fixture alapútvonala PostgreSQL 18); Docling modellek és szükséges PDF/OCR-függőségek. Élő OpenAI/Qdrant nem szükséges az érintett stubos tesztutakhoz. Az offline értékeléshez a Python-környezet és a meglévő fixture/bundle elég.

**Az alábbi parancsok jövőbeli futtatási minták, ebben az auditban nem hajtottam végre őket.** Új, egyedi könyvtárba írnak; nem az eredeti riporthelyeket használják. A teljes pytest saját ideiglenes PostgreSQL-klaszterben adatbázist és tesztadatokat hoz létre, ezért a mostani „nincs adatbázis-módosítás” audit részeként nem futtatható.

```powershell
$runDir = Join-Path (Get-Location) ("evaluation/recheck-2026-11-07-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $runDir | Out-Null
git rev-parse HEAD | Set-Content -Encoding UTF8 (Join-Path $runDir "head.txt")
git --no-optional-locks -c core.fsmonitor=false status --porcelain=v1 |
    Set-Content -Encoding UTF8 (Join-Path $runDir "working_tree_before.txt")
venv\Scripts\python -B -m pip list --format=json |
    Set-Content -Encoding UTF8 (Join-Path $runDir "packages.json")
```

A futtatandó teljes suite előtt/után a **tesztforrásokat és promptokat is magában foglaló manifestet** kell rögzíteni, majd az XML hash-ét ehhez kapcsolni. Az alábbi blokk a már létrehozott `$runDir` változóra épül, nem módosít alkalmazásfájlt:

```powershell
$auditSnapshotCode = @'
import hashlib, json, platform, subprocess
from pathlib import Path
from app.test_data.artifacts import source_hashes
h, sources = source_hashes()
paths = set(sources)
for pattern in ("tests/**/*.py", "tests/fixtures/**/*", "app/prompts/*.txt", "data/synthetic/**/*"):
    paths.update(p.as_posix() for p in Path(".").glob(pattern) if p.is_file())
manifest = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in sorted(paths)}
print(json.dumps({
    "head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "python": platform.python_version(),
    "implementation_sha256": h,
    "files": manifest
}, indent=2))
'@
$auditSnapshotCode | venv\Scripts\python -B - |
    Set-Content -Encoding UTF8 (Join-Path $runDir "source_before.json")

$previousCleanReportDir = $env:CLEAN_INVENTORY_REPORT_DIR
$previousBenchmarkOutput = $env:MATCHING_BENCHMARK_OUTPUT
try {
    $env:CLEAN_INVENTORY_REPORT_DIR = Join-Path $runDir "clean_inventory"
    $env:MATCHING_BENCHMARK_OUTPUT = Join-Path $runDir "inventory_search_benchmark.json"
    # Ha a PostgreSQL binárisok nem az alapútvonalon vannak:
    # $env:MATCHING_TEST_PG_BIN = "C:\Program Files\PostgreSQL\18\bin"
    venv\Scripts\python -B -m pytest -q -p no:cacheprovider --run-docling-pdf --run-matching-postgres "--junitxml=$runDir/test_results.xml"
    $suiteExitCode = $LASTEXITCODE
    $suiteExitCode | Set-Content -Encoding UTF8 (Join-Path $runDir "pytest_exit_code.txt")
}
finally {
    $env:CLEAN_INVENTORY_REPORT_DIR = $previousCleanReportDir
    $env:MATCHING_BENCHMARK_OUTPUT = $previousBenchmarkOutput
}

$auditSnapshotCode | venv\Scripts\python -B - |
    Set-Content -Encoding UTF8 (Join-Path $runDir "source_after.json")
Get-ChildItem -LiteralPath $runDir -File -Recurse |
    Where-Object { $_.Name -ne "artifact_hashes.json" } |
    Get-FileHash -Algorithm SHA256 |
    Select-Object Path, Hash |
    ConvertTo-Json |
    Set-Content -Encoding UTF8 (Join-Path $runDir "artifact_hashes.json")
```

Elvárt artefaktumok: `head.txt`, csomaglista, előtte/utána forrás- és tesztmanifest, `test_results.xml`, exit code, a clean tesztekből új `matching_postgres.json`, `postgres_verification.json`, `scalability.json`, valamint új `inventory_search_benchmark.json`. A manifestek egyezését és a JUnit tényleges counts értékeit ellenőrizni kell; **311 PASS eredményt előre nem lehet garantálni**. A `0 skipped` is ellenőrizendő, mert hiányzó PostgreSQL bináris vagy opt-in kapcsoló kihagyásokat eredményezhet.

### 6.3. Csak szükség esetén: célzott új értékelések

Ezek sem kötelezőek a jelenlegi, forrástartalomhoz igazolt eredmények megtartásához. A `$runDir` az előzőek szerint létrehozott, új könyvtár legyen.

**Régi exact-only/hybrid offline metrikák:**

```powershell
venv\Scripts\python -B -m scripts.evaluate_matching --dataset tests/fixtures/matching_evaluation.json --repeats 5 --output "$runDir/matching"
```

Kimenet: új `matching/matching_metrics.json` és `matching/matching_cases.csv`. Nincs adatbázis- vagy LLM-hívás.

**Clean offline referenciaegyezés:**

```powershell
venv\Scripts\python -B -m scripts.evaluate_clean_inventory --dataset data/synthetic --expected-count 1000 --report "$runDir/matching_offline.json"
```

Kimenet: új `matching_offline.json`. A jelenlegi referencia szerinti 14/16 eredmény esetén a CLI **1-es exit code-ot** ad a két eltérés miatt; ez nem automatikusan futtatási hiba. A riport checks mezőit kell értékelni.

**Meglévő, változatlan clean PostgreSQL read-only újraértékelése:**

```powershell
venv\Scripts\python -B -m scripts.evaluate_clean_inventory --postgres --env-file .env.clean.local --dataset data/synthetic --expected-count 1000 --report "$runDir/matching_postgres.json"
```

Ehhez egy már létező, a bundle-lel egyező `inventory_ai_clean` és megfelelő hozzáférés kell. A CLI előbb ellenőrzi a sémát/adatkészletet, majd read-only egyeztetést végez. Nincs `--apply`, migráció vagy import; ez nem hozza létre a hiányzó DB-t. A shell és a fájl DB-beállításainak eltérését az eszköz elutasíthatja. Ez a parancs a meglévő clean DB-n mér, ezért nem ugyanaz a környezet, mint az eredeti izolált integrációs mérés.

Az eredeti `inventory_search_benchmark.json` pontos tesztmódszere külön így indítható, ha később ténylegesen szükséges; ez saját ideiglenes DB-be ír, most nem futott:

```powershell
$previousBenchmarkOutput = $env:MATCHING_BENCHMARK_OUTPUT
try {
    $env:MATCHING_BENCHMARK_OUTPUT = Join-Path $runDir "inventory_search_benchmark.json"
    venv\Scripts\python -B -m pytest -q -p no:cacheprovider --run-matching-postgres tests/test_matching_postgres.py::test_isolated_inventory_search_benchmark
}
finally {
    $env:MATCHING_BENCHMARK_OUTPUT = $previousBenchmarkOutput
}
```

Ezt a célzott benchmarkot külön új `$runDir` mellett kell használni, ha a teljes suite ugyanabba a könyvtárba már készített ilyen nevű riportot.

## A. melléklet – mind a 84 fájl tételes ellenőrzése

A táblázat **teljes**, nincs kihagyott egyező fájl. Minden sorban a várt SHA-256 egyben a most kiszámított munkakönyvtári SHA-256. A „HEAD” oszlop „azonos” értéke a Git-objektum nyers hash-egyezését, „csak EOL” értéke a 2.2. táblázatban feloldott eltérést jelöli. Így a 69 nyers egyező és a 15 eltérő fájl külön is azonosítható.

| Fájl | Manifest = munkakönyvtár SHA-256 | Munkakönyvtár | HEAD |
|---|---|---|---|
| `app/db/connection.py` | `fd390dd7797175c9297bf4dba60a9ce3a4a0ea60bfb58b02c1cce1172f55d724` | egyezik | azonos |
| `app/db/executor.py` | `b5d4b3eb06c5c91a5feba10e10a8ff3cdb8d7e1db296bcb085396049209513cb` | egyezik | azonos |
| `app/document_processing/__init__.py` | `ceb5757d553b63820c9bfea9ba0a3d0beb960e04d282a407d2e3844249f32f91` | egyezik | azonos |
| `app/document_processing/config.py` | `3fa7daedc5f2251fd1ce75aeeab1bd7bd6160a5f133c9e91744ada58304b95ea` | egyezik | azonos |
| `app/document_processing/docling_parser.py` | `d7ff71215194bb92e4085df555b82cdca844432730a2d6805a74394ad9adf868` | egyezik | azonos |
| `app/document_processing/extraction_service.py` | `31963f1e081142623e6427eebdd557668f76496549338b74aa3881e021f2a778` | egyezik | azonos |
| `app/document_processing/field_mapper.py` | `67e1e3df226d65bb1cfebd55afef31352e062ef641aaa1b17b0381edbbefec70` | egyezik | azonos |
| `app/document_processing/llm_json.py` | `5fa8873fd2406f246ac0a8a400d974ef20764538df75f2ad91580818b24856f1` | egyezik | azonos |
| `app/document_processing/models.py` | `88c2481984cf84d24051514fddf9c756bc6f4dcac6cb54cccbef6db83c73373c` | egyezik | azonos |
| `app/document_processing/processing_service.py` | `59f328ba7ac78bd033c5493dde33aac21dbeff9471968de5db677066123d39e1` | egyezik | azonos |
| `app/document_processing/validation_service.py` | `d489c2dc934a9b296e4e36832e73be81d5762d4578c882a4a71129a0539d6100` | egyezik | azonos |
| `app/errors.py` | `841bc3efe80884c54c9ff6c24af2c397fe3f31562e216919af4604476428edec` | egyezik | azonos |
| `app/evaluation/__init__.py` | `300e04116d0e7ae52e64a254180d20c7c0ed9581af4a7a13948673168eb520f6` | egyezik | azonos |
| `app/evaluation/_build_fixture.py` | `24c72a9c8ca983b64fef1b67d1fc92cb84d1b918b8f00fd356c340e2348c47e6` | egyezik | azonos |
| `app/evaluation/dataset.py` | `0240f2f552bf0ad801608ece2407f199be2e134d755c53028d6fd1b148554fce` | egyezik | azonos |
| `app/evaluation/metrics.py` | `87378a71e499d9ca9e9c44d346785a6746f8ec43ec2e51b9b4aa1d8c7705638f` | egyezik | azonos |
| `app/evaluation/runner.py` | `a1b68c3913bea79bd378f781de2c13587b63221f0e189093d6a16a6a9f6b07a3` | egyezik | azonos |
| `app/orchestration/orchestrator.py` | `ac56581e54c339d078da8a3a29c1f6645b283f5b7fc5495178a46798f1249bf5` | egyezik | azonos |
| `app/rag/embedding/embedding_service.py` | `1f45f1bd7dc6e488d1265f5d5d56b0b489de36a0f2d27c41f1ac7fc6a6da81f6` | egyezik | csak EOL |
| `app/rag/ingestion/chunker.py` | `19a4ddd4d97efd253377266db45b6c73f0b80d4eb54613948e9cca123becbe06` | egyezik | csak EOL |
| `app/rag/ingestion/document_parser.py` | `596a016648b25e6781c71d7d0dc6f4622e90cf1023bab942de92dc1da72e5698` | egyezik | azonos |
| `app/rag/ingestion/ingestion_service.py` | `75a793be49a0866550aa61b03e4a1c7ebddd8202acff34a090fc7d6aae58cd7d` | egyezik | azonos |
| `app/rag/ingestion/parser.py` | `4b744f5d611277b7696d4dffbee13e77573c66aeb2d67ed64e57c79e95a847e6` | egyezik | csak EOL |
| `app/rag/models/rag_models.py` | `8faca5e7a92d65f6d337ca86310e003a5c45ba4ccbc1d243dde1824c2827a7b6` | egyezik | csak EOL |
| `app/rag/retrieval/rag_service.py` | `83308d98351f5f667898a9c9b7d040b8cd81fc1ae3f93778c1ab90f4496c2c1c` | egyezik | azonos |
| `app/rag/retrieval/retriever.py` | `cfff8bf5ff6b17c98cf447a508a92a4056120b7b82acdcd9d4f854420222389c` | egyezik | csak EOL |
| `app/rag/vector_store/qdrant_client.py` | `70bccf3b871b5c059060a77b5fa37f92dfd398f7e2a3fcdeb3e100615d41db62` | egyezik | csak EOL |
| `app/record_matching/__init__.py` | `3615c329fb53c2a965ad7884a7332a4566f0064b872a511deb760ca7778e5aa2` | egyezik | azonos |
| `app/record_matching/candidate_service.py` | `c889ebd03dd7c77191453b5fcb3be6d3e6d8f4bc36eff14b67a1dad3115232e6` | egyezik | csak EOL |
| `app/record_matching/comparison_service.py` | `515e9fb2b767f9d741fdb8fc52d2acda79303446fa3abdfe43698b8ab9933da2` | egyezik | azonos |
| `app/record_matching/config.py` | `cc9b61c026919d5da0e795011d013a8010bbeebcc88471ca7f38511f91822654` | egyezik | azonos |
| `app/record_matching/inventory_audit.py` | `3a3de1b2a82cc7924cc353b5dfba760ff666d6a06e66e6b4b549cdcafa8834f5` | egyezik | azonos |
| `app/record_matching/matching_engine.py` | `ec5e20c195801271a85e204c71b689a61bfe4ffb0d00bb6a3d17fa796e4bc7e3` | egyezik | azonos |
| `app/record_matching/models.py` | `488712b35893fde97068a13e8b4943cdeae3976c9ed02afd47091d359e0124a8` | egyezik | azonos |
| `app/record_matching/normalization.py` | `1c01621dcdeee29f8e7301ce607c596c0ae3013a7a241341c475ca9f401640ff` | egyezik | azonos |
| `app/record_matching/preparation.py` | `4d0b407daab3ddba4c6e4110db3b6964084e786219a8142fb469f61a6f2e1284` | egyezik | azonos |
| `app/record_matching/reconciliation_service.py` | `b95d81b0bd210fc2eba054f5d591a7e2da030de184ba79523b07150cbc371cd1` | egyezik | azonos |
| `app/record_matching/repository.py` | `56d0a2bfa40facffa5a57ae7e4fd76580172326ad5ba611add0b1c85bfe83b1d` | egyezik | csak EOL |
| `app/record_matching/suggestion_engine.py` | `95f41c7277d3a97b67f02cf975496ea4b3f054d980801ee0ff17a1526e8d29d7` | egyezik | azonos |
| `app/security/guardrails.py` | `ee3d37e8b13766b427e1ec918dba37055156db3e03f3e890a9dd89107ec1792d` | egyezik | azonos |
| `app/security/injection_checks.py` | `feba420d24f93c33adf8bf547ec3921038434239b5933d07108ddca41f1ac9f2` | egyezik | azonos |
| `app/security/sql_validator.py` | `5c12a4792dae0a15f14d52277a072e65d1a5c736afebfa530fb8a0933e809a20` | egyezik | azonos |
| `app/services/answer_service.py` | `fcf9fb2b8b1a998d85081baa2438d9fc992dd4eb1477116ae31ac3fa21af5aa8` | egyezik | azonos |
| `app/services/llm_service.py` | `d366626fe609ab15c9454b55825dc219a6dd9a68c5e5950cdac0bc5b6b3dd34f` | egyezik | azonos |
| `app/services/routing_service.py` | `5e3a8acac1afae6c468d6e1cf24ff854c01337ab802c586c09838c6457b1164f` | egyezik | azonos |
| `app/services/schema_service.py` | `40c7d435c2a8000e70165d8d28db778ef24d916ee4883f84c87398f5e90c4868` | egyezik | csak EOL |
| `app/services/sql_generation_service.py` | `6fe83c209613cd7356d46298a5b518e441e7c67126a670332e235ee0ccbd5f86` | egyezik | csak EOL |
| `app/test_data/__init__.py` | `df6e4e5f5dbdee9364fbf93b646157ee6d1517bad31880584fcaef61b91b6b14` | egyezik | azonos |
| `app/test_data/artifacts.py` | `3cc00d27ec007485e836f34483b9c79dc3eaaa16a012d7f95c0224adb82cc5be` | egyezik | azonos |
| `app/test_data/catalog.py` | `728be3e4f2ae14312fdf211821496374b6d529af1cd2280a9b6e87824ac285a2` | egyezik | azonos |
| `app/test_data/cli.py` | `bcbc81d98ef7239e1b74595e0f6c5e513d55475815a389d737bd39dd31197379` | egyezik | azonos |
| `app/test_data/database.py` | `927d6bfb703a6954a701d11b49143cb0c1897fd3baf7b10dfa74717a66c969d1` | egyezik | azonos |
| `app/test_data/documents.py` | `f85cf1e07e5190deab57671701da9a94dc2e6e94dcb155f40bb8e6956416ce6f` | egyezik | azonos |
| `app/test_data/evaluation.py` | `3e65aa0ad952d338c788072221489e1589f05db4edebaaf0d54f2d3500e23164` | egyezik | azonos |
| `app/test_data/generator.py` | `967310b0abc261162be54d3d5e3673c02c5d1570c719c95740a3ce8a60a309e7` | egyezik | azonos |
| `app/test_data/models.py` | `a09d6a98ebdfabb3b9b4a8f37e9481c419d299f19de134ed18ece58e9258c1ee` | egyezik | azonos |
| `app/test_data/validation.py` | `16710e20af1f6671393617d924ffc0ab1979c9b2b53da34af36da10c78c223d2` | egyezik | azonos |
| `app/web/__init__.py` | `9d975f23d1e192a593dddca637d530127638ccaf5fd7d8d2564ede2a0a128357` | egyezik | azonos |
| `app/web/document_preview.py` | `bad07d674a9ef89ae0d5ee53afe797b09f2accf227c0afaa288dc951ac557ebe` | egyezik | azonos |
| `app/web/reconciliation_preview.py` | `644576368ca7846ef010eadd9ce3659e3709454b86d75b6c4e56531802950d7e` | egyezik | azonos |
| `app/web/simple_server.py` | `ad5a8ad502c9a2aca0160d109bbaa9156556515faa83278ea9eac8399f359c32` | egyezik | azonos |
| `config/column_mapping.yaml` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | egyezik | azonos |
| `config/schema_descriptions.yaml` | `714f049c9d2cbf007009fbe91ef035db663171cc51c744f56bb1a74a12092afc` | egyezik | csak EOL |
| `config/schema.json` | `8195648a26fc5bf0a85329c4240b8a0f133c8af4e3230e7f3a040a9390970a7e` | egyezik | csak EOL |
| `migrations/001_inventory_number_unique_rollback.sql` | `7b2befa565cac58411739e2a7195c3183617701ef65541773f365f1546cff99e` | egyezik | azonos |
| `migrations/001_inventory_number_unique.sql` | `a04347b85bfd8faae7fa2c5512ba45d3a598952c9caf633688cb54faef49601a` | egyezik | azonos |
| `migrations/clean/001_create_inventory_items.sql` | `b7c81ae63949d85f9a4f43f8b3797371d7d971a1db4d62096b5e4a1585e98b41` | egyezik | azonos |
| `migrations/clean/002_add_inventory_constraints.sql` | `1121cbba1e9ef40e248ad3bf669cec8fa0dcc084f21e2503d46e8b61df5ca809` | egyezik | azonos |
| `migrations/clean/create_database.sql` | `907a10acf31d42a1eea3cef1ff64231ac0b1186d6812b1b9b08e5acd726f09ab` | egyezik | azonos |
| `requirements-dev.txt` | `5db75c0524617c465009cfd230e3b20346b6e0cd1f755673b8e1140ea145a849` | egyezik | azonos |
| `requirements.txt` | `cf77a799e45fe50dfd7733efde9ccadd7a726a2eed5b697a9ff863f377becb66` | egyezik | csak EOL |
| `scripts/audit_inventory_numbers.py` | `5c2cb70a3c3d2b71a480d98e4dbf53895e1a83553a075133bfb35ff6cb785530` | egyezik | azonos |
| `scripts/audit_matching_schema.py` | `ac3656ee215aebb21fda2035372504db2e0dc2940aac9ba62b50db4f0e091ee2` | egyezik | csak EOL |
| `scripts/evaluate_clean_inventory.py` | `0587598d61a58ccf126951ec0f92b88c4417d34433e2b4dbb7c73436bbfe01de` | egyezik | azonos |
| `scripts/evaluate_matching.py` | `80bfcfffc87b0b023fe4beb867c5778d15b8fa45116b93d06e8b73048d5a42ef` | egyezik | azonos |
| `scripts/extract_schema.py` | `dc1f5ab37cf131f53ba1dafd53f5fbe4ef3e3ea013448af837b9159f85a5844c` | egyezik | csak EOL |
| `scripts/generate_inventory_data.py` | `e7f9b429640f2dee4cd47ebe56287567d5c9658f4e1e82f70fd29d3e737ddd44` | egyezik | azonos |
| `scripts/load_inventory_data.py` | `c0b207781fbf3aa7295b8bd92d381b14b3f547c881345cdde5214e19d167a3cb` | egyezik | azonos |
| `scripts/prepare_docling_models.py` | `4e1f353894b434aec9a013afb6f366ea8552ebdcd67248ec16f45dc155c854cb` | egyezik | azonos |
| `scripts/prepare_inventory_database.py` | `ff0ae5b15d325c1a36b85ce74aa88664575fd3cb41c12a6fd5b01988550a6290` | egyezik | azonos |
| `scripts/run_webapp.py` | `ca1d3476e26ff82b64297ec42d70fa160b0cdd79ebbd677b295df391bf0dac9c` | egyezik | azonos |
| `scripts/verify_clean_inventory_report.py` | `034ef27388c15a8a210e3030bb8561114ac02186d63c5257ec5761e1235b5f79` | egyezik | azonos |
| `scripts/verify_inventory_data.py` | `8fa8eddec6beaf986935e9cf3580c1b52f080383870c39ecc661625882545a77` | egyezik | azonos |
| `scripts/verify_matching_report.py` | `4378ad9b6faac74bcb12f8da7915f45903d02920437be96bee4e8a00b585bb15` | egyezik | azonos |

## B. melléklet – a vizsgált riportfájlok azonosítása

Ezek a riportok aktuális **fájlhash-ei**, nem a bennük tárolt aggregált implementációhash-ek.

| Riport | Fájl SHA-256 |
|---|---|
| `evaluation/clean_inventory/matching_offline.json` | `b426e213232461604b6813c7f88997ea8f1333dcfeecb3460ce9253dd46e5361` |
| `evaluation/clean_inventory/matching_postgres.json` | `46dc778fc793864a6268cff5e3235f576cbec4d6059a885bcdb6f69ded3639d1` |
| `evaluation/results/matching_metrics.json` | `2ea772f5732285032723fc195ce55a5bb4a2aafc2c52cbe8c698082b377fc53d` |
| `evaluation/results/inventory_search_benchmark.json` | `e4cb748f3c035f38e3d0364d3e4cbd01290a91024ddd2571ec69360bed439aa2` |
| `evaluation/clean_inventory/test_results.xml` | `b4f924371cca5e3c93f1eb2c369ccfe476f5cc4fab54f8cc4f51e9dde9dac3fe` |

## Záró válasz

**Végső változatlansági ellenőrzés:** az audit közben és a dokumentum elkészülte után összevetett 169 alkalmazás-, script-, konfigurációs, teszt-, adat- és riportfájl közül egyik sem változott, és ezekben a könyvtárakban új fájl sem keletkezett. A korábbi technikai átadás hash-e is változatlan. A Git végső állapota csak a már korábban is nem követett átadást és ezt az új auditriportot mutatja.

**Igen: a jelenlegi InventoryAI implementációhoz hitelesen felhasználhatók a meglévő matchingmetrikák, a 14/16 referenciaegyezés és a megfelelően körülhatárolt történeti futásidők. A 15 Git/export-hash eltérés csak sorvégkülönbség, ezért ezek miatt nem szükséges mérésismétlés. A 311 tesztes eredmény dátumozott korábbi JUnit-ként használható; a mai commit teljes tesztfutásának közvetlen igazolásához további verzióhoz kötött bizonyíték vagy új tesztfutás kell.**

