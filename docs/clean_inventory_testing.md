# Clean készlet: tesztelés és mérési határok

## Négy külön ellenőrzési szint

1. **Adatkészlet:** tiszta Python, valódi CSV/JSON/manifest. Szabályok, seed,
   hash, pénzügyi/dátum/katalógus-konzisztencia és dokumentumreferenciák.
2. **Adatbázis-integráció:** valódi, ideiglenes PostgreSQL, külön porton és
   adatkönyvtárral. Valódi migráció, constraints, batch import, rollback és SELECT.
3. **Dokumentumok:** mind a 32 fájl valódi PDF/DOCX, Doclinggal külön beolvasva.
   D01 és D02 mindkét formátumán a teljes `process_document()` és PostgreSQL-
   egyeztetés is lefut, de az LLM válaszait előre megadott tesztválasz helyettesíti.
4. **Élő LLM:** ezen készlet élő OpenAI-val végzett mezőkinyerési/mapping-
   pontossága nincs megmérve. A parserpróba és a tesztválaszos pipeline ezt nem igazolja.

A fájlok feldolgozhatóságát bizonyítottuk a parser szintjén. A teljes élő AI-
pipeline-t nem jelöljük teszteltnek. A felhasználó ezt a telepített clean DB-n
a [kézi útmutató](clean_inventory_database.md) D01/D02 lépéseivel tudja kipróbálni.

## Reprodukálás

```powershell
venv\Scripts\python -m pip install -r requirements-dev.txt
venv\Scripts\python -m pytest -q
```

Az alapértelmezett futás kihagyja az opt-in PostgreSQL- és PDF-próbákat.
A teljes, ténylegesen ellenőrzött konfiguráció:

```powershell
$env:CLEAN_INVENTORY_REPORT_DIR = "evaluation/clean_inventory"
venv\Scripts\python -m pytest -q --run-docling-pdf --run-matching-postgres --junitxml=evaluation/clean_inventory/test_results.xml
```

PostgreSQL `initdb` és `pg_ctl` kell. Windows alapútvonal:
`C:/Program Files/PostgreSQL/18/bin`; más telepítésnél állítsd a
`MATCHING_TEST_PG_BIN` változót. A teszt saját `127.0.0.1` klasztert indít,
ideiglenes porttal; nem használja az alkalmazás `DB_*` beállításait.
A 10 000 soros teszt külön ideiglenes klaszterben fut. A szervereket a fixture
a futás végén leállítja. A lokális tesztklaszter trust hitelesítése kizárólag
a loopbacken elérhető, rövid életű fejlesztői tesztkörnyezethez tartozik.

A PDF-próbákhoz a Docling modelleknek elérhetőknek kell lenniük. Előkészítés:

```powershell
venv\Scripts\python -m scripts.prepare_docling_models
```

Ez a külön modell-előkészítés használhat internetet; a szintetikus rekord- és
dokumentumgenerálásnak nincs hálózati igénye.

## Új automatizált tesztek

| Tesztfájl | Bizonyított feltétel |
|---|---|
| `test_inventory_data_generator.py` | 1000 rekord; egyediség; quantity; eltérő seedek; azonos seed reprodukció; 1/7/5000/10000 sor; katalógus; árak/dátum/helyszín; szigorú típusok; CSV/JSON; manipulált hash; valódi PDF/DOCX tartalom; dokumentum-byte-determinizmus |
| `test_inventory_seed_loader.py` | Rossz DB_NAME még kapcsolódás előtt elutasítva; pontos jóváhagyás; shell/env konfliktus; titokmentes CLI-hibák |
| `test_inventory_clean_integration.py` | Külön create/migrate; dry-run; kétszer alkalmazható séma; batch után mesterséges hiba és teljes rollback; azonos seed újrafuttatása; eltérő készlet elutasítása; tényleges current_database guard; constraints; sémaeltérés; SQL/egyeztetés/Streamlit; Docling; olvasószerep |
| `test_inventory_scalability.py` | 10 000 rekord, két párhuzamos betöltő, egyetlen végleges készlet, hash, célzott keresés 1-es limit mellett |

A PostgreSQL negatív tesztek módosításai kizárólag az elkülönített tesztadatbázis
tranzakcióiban történnek, rollbackkel. A külön `inventory` nevű őrtábla is ebben
az ideiglenes klaszterben van: előtte/utána ugyanazt az értéket kell tartalmaznia.
Ez a célvédelmet teszteli, nem az üzleti adatbázis új élő auditja.

A korábbi 202 teszt megmaradt. A teljes futás nyers bizonyítéka:
[test_results.xml](../evaluation/clean_inventory/test_results.xml).
A végleges összesítést a [megvalósítási riport](clean_inventory_report.md) tartalmazza.

## A 16 dokumentumeset mérése

```powershell
venv\Scripts\python -m scripts.evaluate_clean_inventory --report evaluation/clean_inventory/matching_offline.json
```

Ez a **valódi változatlan egyeztetőt** futtatja ismert strukturált mezőkkel és
memóriában helyettesített SQL-sorbeolvasással. A meglévő `FixtureRepository`
használatával a keresési szakaszok vezérlése is az alkalmazásé marad.
Az izolált PostgreSQL-es teszt ugyanazokat a dokumentumeseteket valódi SQL-lel
is futtatja, és az eredményeket összeveti az offline mérésével.

Az ellenőrzött dimenziók:

- kategória;
- kiválasztott fizikai rekord leltári száma;
- mezőeltérések neve, adatbázisértéke és dokumentumértéke;
- javasolt műveletek halmaza;
- emberi ellenőrzési igény.

**Offline eredmény: 14/16 teljes referenciaegyezés, 2 eltérés.** Az eltérések:

| Eset | Üzleti referencia | Tényleges eredmény | Ok |
|---|---|---|---|
| D05 | AMBIGUOUS_MATCH | SEARCH_INCOMPLETE + MANUAL_REVIEW | Hiányzó leltári szám után a fuzzy névkeresés több mint 100 releváns jelöltet talál; a kandidánslista korlátozott. |
| D06 | CONFLICTING_DATA | SEARCH_INCOMPLETE + MANUAL_REVIEW | A leltári szám egyezik, a cikkszám ellentmond. Nincs korai célzott siker; a széles fuzzy keresés korlátja miatt a végső státusz a hiányos keresést jelzi. Az item_code eltérés megmarad. |

Mindkét esetben tartózkodik a rendszer, nem csatol önkényesen rekordhoz és nem
javasol új rekordot. A két eltérő kategóriát **nem számítjuk sikeres referencia-
egyezésnek**, és nem módosítottuk az algoritmust vagy küszöbeit jobb pontszámért.
A D12 kritikus modellellentmondás és a D15 két eszköz miatti blokkolás sikeres.

Az értékelő 1-es exit kódja ezért ennél a rögzített 16 esetes referenciahalmaznál
várható. Ez nem az importer hibája. A pytest ezzel szemben azt ellenőrzi, hogy
az infrastruktúra és az eltérések kimutatása helyesen működik; a két ismert
kategóriaeltérést nem alakítja át mesterséges pytest PASS üzleti állítássá.

Fájlok:

- [Offline mérés](../evaluation/clean_inventory/matching_offline.json)
- [Valódi izolált PostgreSQL-mérés](../evaluation/clean_inventory/matching_postgres.json)
- [Import és adatbázis-verifikáció](../evaluation/clean_inventory/postgres_verification.json)
- [10 000 soros mérés](../evaluation/clean_inventory/scalability.json)

## Lenyomatok és történeti eredmények

```powershell
venv\Scripts\python -m scripts.verify_clean_inventory_report
```

Ellenőrzi a hivatalos CSV/JSON/dokumentumcsomagot és a négy új mérési riport
forrás-hashét. A forráslenyomat az alkalmazás, scriptek, config, a clean almappát
is beleértve minden SQL-migráció és a függőségi fájlok bájtjaira épül.
Forrás-sorvég vagy függőségi fájl változása is új lenyomatot eredményezhet;
az adatkészlet saját kanonikus hash-e ettől független.

Az `evaluation/results/` korábbi 74 esetes mérései és élő auditjai megmaradtak.
Az új fájlok miatt a régi teljes-repository hash természetesen már nem a jelen
forrást írja le. Az új riportok külön `evaluation/clean_inventory/` könyvtárba
kerülnek, és nem írják át a történeti számaikat.

## Korlátok

- A 16 ismert szintetikus eset fejlesztői ellenőrzőkészlet, nem független,
  reprezentatív vállalati pontossági mérés. A 14/16 nem LLM-accuracy.
- A valós pénzügyi/számviteli feltevéseket a szintetikus modell nem bizonyítja.
- A 10 000 soros mérés helyi, egyszeri próba; nincs többfelhasználós üzemi
  teljesítménygarancia vagy hálózati késleltetésre vonatkozó általánosítás.
- SQL: valódi executor és adatbázis; a természetes nyelvi SQL/answer választ
  a smoke teszt helyettesíti. RAG/HYBRID: vezérlési/regressziós ellenőrzés
  külső AI-/dokumentumkeresési tesztválaszokkal. Élő Qdrantot nem szinkronizáltunk.
- Az app meglévő 100-as kandidánslimitje szándékosan megmaradt.
- A helyi adatbázis telepítése és a `.env` átállítása külön felhasználói művelet.
