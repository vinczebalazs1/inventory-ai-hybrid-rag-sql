# Rekordegyeztetés és döntéstámogatás

## Cél és architektúra

A modul egy már feldolgozott dokumentum adatait hasonlítja össze a PostgreSQL
leltárrekordjaival. Rangsorolt találatokat, mezőszintű összehasonlításokat és
indokolt műveleti javaslatokat ad. A dokumentumelemzés `ProcessingResult`
interfésze változatlan marad; az egyeztetés külön indítható szolgáltatás.

```text
PDF/DOCX → Docling → LLM extraction → LLM mapping → normalizálás/validáció
                                                              ↓
                                                     ProcessingResult
                                                              ↓
                                              reconcile_document(result)
                                                              ↓
                                         Dokumentumadatok előkészítése
                                                              ↓
                                      PostgreSQL sémaellenőrzés és keresés
                                                              ↓
                                      Determinisztikus rangsorolás/döntés
                                                              ↓
                                      Mezőösszehasonlítás és javaslatok
                                                              ↓
                                                ReconciliationResult
                                                              ↓
                                                 Streamlit áttekintés
```

A rekordegyeztető nem hív LLM-et és nem használ Text-to-SQL lekérdezésgenerálást.
A korábbi SQL/RAG/HYBRID kérdezés és a Qdrant-feltöltés külön útvonalon működik.
Az egyeztetés nem hoz létre tartós dokumentum–rekord kapcsolatot: a
`ATTACH_DOCUMENT` is csak megjelenített javaslat. Az üzleti adatbázis sémáját és
tartalmát ez a modul nem módosítja.

## Bemenet és adatminőség

A bemenet a meglévő `ProcessingResult`: parsereredmény, extraction, mapping és
validációs jelzések. A normalizált értékek mellett megmarad a forráscímke, a
nyers érték, az evidence és az oldalszám. Az evidencia forrásbeli jelenléte nem
bizonyítja az LLM szemantikai értelmezésének helyességét.

A lapos mezőlista nem tartalmaz teljes eszközönkénti csoportosítást. Egymásnak
ellentmondó mezőértékek vagy több eszközre utaló adatok esetén a modul emberi
ellenőrzést kér; nem egyesíti ezeket önkényesen egy leltárrekorddá.

A sorozatszám és a Service Tag nem belső leltári azonosító. A repository jelenlegi
fájlsémájában nincs külön sorozatszám-, gyártó- vagy modellmező. A támogatott
azonosítókat a tényleges séma korlátozza; új oszlop nem keletkezik automatikusan.

## Modulok és nyilvános API

| Fájl az `app/record_matching/` mappában | Feladat |
|---|---|
| `models.py` | Strict Pydantic inputközi és eredményszerződések, enumok |
| `config.py` | Validált, változtathatatlan konfiguráció |
| `normalization.py` | Azonosító-, szöveg-, dátum- és decimális összehasonlítás |
| `preparation.py` | Validáció, evidenciaellenőrzés, ismétlés és konfliktus, többeszközös blokkolás |
| `repository.py` | Sémavizsgálat, ellenőrzött rekordazonosítók, paraméterezett SQL |
| `candidate_service.py` | Korlátos jelöltválogatás, előrangsorolás, SQL keresőtokenek |
| `matching_engine.py` | `MatchingEngine.score()` és `match()`, vétók és döntés |
| `comparison_service.py` | `compare_fields()`, típushelyes mezőeltérések |
| `suggestion_engine.py` | `suggest_actions()`, kizárólag tanácsadó műveletek |
| `reconciliation_service.py` | Nyilvános API, szakaszonkénti hibakezelés és mérés |

```python
from app.record_matching.reconciliation_service import reconcile_document

# A korábban elkészült process_document(...) eredménye:
reconciliation = reconcile_document(processing_result)
serialized = reconciliation.model_dump_json(indent=2)
```

Tesztekhez a `repository`, `settings` és `columns` kulcsszavas argumentumok
beadhatók. A repository szerződése:
`search(values, expected_columns, settings) -> CandidateSearchResult`.
Az eredeti `process_document(file_bytes, filename)` változatlan.

A `ReconciliationResult` tartalmazza a dokumentum nevét/típusát, a matching
státuszt, az ellenőrzési igényt, a kiválasztott rekordot, a jelölteket,
összehasonlításokat, javaslatokat, indokokat, figyelmeztetéseket, validációs
összegzést, keresési és időmérési metaadatokat. A `prepared_document` megőrzi
az összes mező eredetét és validációs állapotát konfliktus vagy sikertelen
egyeztetés esetén is. A többlet attribútumok és a nem véges számok tiltottak.
JSON-visszaolvasáshoz `ReconciliationResult.model_validate_json()` használható.

## Előkészítés és normalizálás

- Az eredeti mapping nem módosul. Csak korábban validált, újból ellenőrzött
  érték kerül keresésbe; a nyers értékből levezethetőséget is vizsgáljuk.
- Azonos célsémamező azonos összehasonlítási értéke ismétlés. Az összes
  előfordulás megmarad. Két eltérő érték blokkolja az egyeztetést.
- Kitöltött és explicit üres érték együtt szintén konfliktus.
- Több eszközsort tartalmazó Markdown-tábla, illetve ismételt, eltérő
  sorozatszám/service-tag címkék több entitásra figyelmeztetnek. Ezeket nem
  csoportosítjuk találgatással. Ez konzervatív felismerés, nem általános
  dokumentum-entitásszegmentálás; a parser/extraction kihagyásait nem oldja meg.
- Az evidence szövegnek a forrásban és – ha van – a megadott oldalon szerepelnie
  kell, valamint tartalmaznia kell a nyers mezőértéket. A hiányzó evidence
  felülvizsgálatot és a csatolási/frissítési javaslat visszatartását okozza.
- Azonosító: NFC és külső whitespace levágása. Betűméret, belső whitespace,
  vezető nullák, kötőjelek megmaradnak. Szabad szöveg: NFKC, casefold,
  whitespace-összevonás. Írásjelek általános törlése nincs.
  Az adatbázis azonosítóját a tárolt alakjában hasonlítjuk össze; az adatbázisban
  levő `A` és ` A ` nem olvadhat össze egy UNIQUE kulcs feltételezett egyenértékűségévé.
- Az összegek egész számból vagy pontos decimális sztringből, `Decimal`
  használatával hasonlíthatók össze. Pénzügyi float bemenet elutasított.
  A kimenet JSON-kompatibilis egész vagy kanonikus decimális sztring.
- Dátum: validált ISO-dátum. A modellnév számot tartalmazó tokenjei külön
  ellenőrzöttek: a `5540` és `5550`, illetve `X1` és `X2` különböző.

## Adatbázisséma, rekordazonosság és keresés

A 2026-10-10-i, kizárólag metaadatokat olvasó ellenőrzés eredménye:
az `inventory_items` 11 oszlopa egyezik a sémafájllal; nincs PRIMARY KEY vagy
teljes UNIQUE index. Gépi bizonyíték: [schema_audit.json](../evaluation/results/schema_audit.json).
Ezért az aktuális üzleti táblából a rendszer nem ad igazolt `EXACT_MATCH`
státuszt vagy konkrét rekordra irányuló csatolási/frissítési javaslatot.
A lehetséges egyezéseket és eltéréseket továbbra is megmutatja.

Minden keresés saját `REPEATABLE READ`, `READ ONLY` tranzakciót használ.
A konfigurációból engedélyezett tábla és oszlopok `psycopg2.sql.Identifier`
objektumok; a dokumentumból származó értékek kötött SQL-paraméterek.
A kapcsolat és cursor kivételkor is lezárul. Nincs üzleti DDL, DML,
Text-to-SQL, automatikus index- vagy `pg_trgm`-telepítés.

Az élő sémán oszlopneveket, típusokat és az indexek állapotát ellenőrizzük.
Részleges, kifejezéses, érvénytelen vagy halasztott egyediség nem bizonyít
stabil azonosságot. Egy nullable UNIQUE kulcs csak nem NULL értékű sorban
alkalmas azonosításra. Az azonosító a valódi kulcsmezők kanonikus JSON-ja;
sem sorszámot, sem PostgreSQL `ctid` értéket nem nevezünk tartós rekordkulcsnak.
RLS és hagyományos táblaöröklés mellett a teljes keresést nem állítjuk igazoltnak.

Keresési lépések:

1. `inventory_number` vagy `item_code` pontos egyezése, OR kapcsolattal,
   hogy az egymásnak ellentmondó azonosítóhivatkozások is látszódjanak.
2. Egyetlen, igazolt egyedi azonosítóegyezés lezárhatja az adott azonosság
   keresését (`verified_identifier` scope). Ez nem a teljes tábla bejárása.
3. Egyébként legfeljebb `max_scan_rows + 1` soros vizsgálat. A plusz sor jelzi
   a korlát túllépését. Kis táblán minden sort megvizsgálunk, majd jelöltet válogatunk.
4. Nagyobb táblán SQL-szűrés: `item_code + sub_code`, `name + location`,
   `name + activation_date`, valamint legfeljebb 8 névtoken `ILIKE` keresése.
   A LIKE metakarakterek escape-eltek. Ez a tartomány mindig részleges.
5. A jelölteket pontos azonosító, összetett kód, névhasonlóság és stabil
   tartalmi rendezés sorolja előre. A végső rangsort a külön matcher számolja.

A lekérdezések eredményét korlátozzuk, de a PostgreSQL végrehajtási terve
index nélkül továbbra is bejárhatja/rendezheti a táblát. A statement timeout
korlátozza ezt; nagy adatbázisra indextervezés és valós teljesítménymérés szükséges.
Az eldobott jelöltek, timeout és szűrt részhalmaz `SEARCH_INCOMPLETE` állapotot
okoznak. Ilyenkor nincs újrekord-javaslat. Exact-only módban a teljesség csak
a pontos azonosítókeresés tartományára vonatkozik, ezért abból sincs létrehozási javaslat.

## Pontozás és döntési szabályok

Az alapképlet: `S = Σ(w_f × s_f) / Σ(w_f)`, ahol a nevező a dokumentumban
rendelkezésre álló, validált egyeztetési mezők súlyait tartalmazza.
Hiányzó adatbázismezőhöz 0 hasonlóság tartozik; a mező súlya megmarad.
Hiányzó dokumentummező egyik összegben sem szerepel. Pénzösszeg nem pontozási jel.

| Mező | Súly | Hasonlóság |
|---|---:|---|
| inventory_number | 0,5 | Konzervatív pontos egyezés |
| item_code | 0,4 | Konzervatív pontos egyezés |
| sub_code | 0,1 | Pontos egyezés |
| name | 0,3 | max(ratio, token_sort_ratio) / 100 |
| location | 0,1 | Normalizált pontos egyezés |
| activation_date | 0,1 | ISO-dátumegyezés |

A névmetrika teljes sztringet használ; nem használ részsztringre tökéletes
pontot adó `partial_ratio` vagy `token_set_ratio` metrikát.
Hivatkozás: [RapidFuzz API](https://rapidfuzz.github.io/RapidFuzz/Usage/fuzz.html).

Az alapképlet után alkalmazott, magyarázatban megjelenő szabályok:

- Igazolt egyedi azonosítókulcs egyezése 1 pont. Összetett azonosítóhoz minden
  kulcsrész dokumentumbeli egyezése szükséges. Egyéb stabil DB-kulcs puszta
  létezése nem változtatja a névegyezést pontos azonosítóegyezéssé.
- Nem igazoltan egyedi, de pontos azonosítóegyezés alsó pontkorlátja a likely
  küszöb. Egyediség nélkül minden pontszám legfeljebb `exact_threshold - 0,001`.
- Ellentmondó azonosító vétó: 0 pont. Eltérő modellszámtokenek vagy nagyon
  eltérő név esetén legfeljebb `model_conflict_cap`, és a jelölt nem választható.
- Az alapértelmezett küszöbök: exact 0,95; likely 0,72; közeli jelöltek közti
  margin 0,05; előszűrés/duplikációgyanú 0,45; modellkonfliktus-korlát 0,4.
- Azonos pontnál a rekordkulcs és a mezők kanonikus JSON-ja stabil rendezést ad.
  A sorrend nem oldja fel a bizonytalanságot.

| Státusz | Feltétel |
|---|---|
| CONFLICTING_DATA | Ellentmondó dokumentumadat vagy pontos azonosító melletti kritikus eltérés |
| INSUFFICIENT_DATA | Nincs valid azonosító vagy kellően leíró név; egyetlen általános szó nem elég |
| SEARCH_INCOMPLETE | A releváns keresés teljessége/sémája nem igazolt |
| AMBIGUOUS_MATCH | Több nem egyértelmű azonosítóegyezés vagy a vezető jelöltek közti kis margin |
| EXACT_MATCH | Ellenőrzött egyedi azonosító, megfelelő pont, teljes releváns keresés, kritikus konfliktus nélkül |
| LIKELY_MATCH | Egyértelmű vezető jelölt a likely küszöb felett; emberi ellenőrzéssel |
| NO_MATCH | A befejezett keresési tartományban nincs elfogadható jelölt |
| ERROR | Konfigurációs, adatbázis- vagy feldolgozási hiba; biztonságos, szakaszhoz kötött üzenet |

A leíró név legalább két szóból áll vagy számot tartalmaz. A `NO_MATCH` is
tartalmazhat megvizsgált, elutasított jelölteket. Például eltérő modellszámú
névjelölt pontos azonosító nélkül nem bizonyít adatellentmondást egy azonosított
rekordban; nem választjuk ki, és emberi ellenőrzést kérünk.
Az evidenciahiány vagy hibás nem azonosítómező mellett a tényszerű kulcsegyezés
státusza megmaradhat, de az eredmény ellenőrzést igényel.

Az `exact_only` stratégia ugyanazokat a biztonsági vétókat, összehasonlítást és
javaslatszabályokat használja; jelöltet kizárólag pontos azonosító alapján keres.
A pontszámok és küszöbök mérnöki szabályok, nem kalibrált valószínűségek.

## Mezőeltérések és javaslatok

| Összehasonlítás | Jelentés |
|---|---|
| EQUAL | Validált, összehasonlítható értékek egyeznek |
| DIFFERENT | Mindkét oldalon ismert, érvényes értékek eltérnek |
| UNKNOWN | Hiányzó dokumentummező vagy ismeretlen DB NULL érték |
| INVALID | Hibás/ellentmondó dokumentummező |
| NOT_COMPARABLE | Explicit üres/null dokumentumadat, nem normalizálható DB-adat, eltérő/hiányzó pénznem |

A hiányzó mezőből nincs törlési javaslat. DB NULL esetén nem állítunk bizonyított
értékváltozást. Pénzösszeget csak egyező, felismert pénznemben hasonlítunk össze;
nincs árfolyamkonverzió. A bizonyíték, oldalszám, eredeti és normalizált érték
minden összehasonlításnál megmarad. LIKELY jelöltnél az eltérések tájékoztató jellegűek.

- `ATTACH_DOCUMENT`: kizárólag EXACT és stabil rekordkulcs, minden átadott mező
  validált, visszakereshető bizonyítékkal. Ez továbbra is tanácsadó eredmény.
- `UPDATE_CANDIDATE`: az előző feltételek mellett tényleges mezőeltérések.
  Mindig emberi felülvizsgálatot igényel. Pénzügyi/azonosítómezőn külön korlátjelzés.
- `CREATE_RECORD_CANDIDATE`: teljes táblán befejezett hibrid keresés, NO_MATCH,
  validált név és legalább egy azonosító, evidencia, konfliktus és közeli névjelölt
  nélkül. Megadja a rendelkezésre álló és hiányzó mezőket; mindig review szükséges.
- `MANUAL_REVIEW`: bizonytalan, hibás, hiányos, nem összehasonlítható adatoknál,
  illetve minden módosítási/létrehozási javaslatnál.

Minden javaslat `executable=False`; végrehajtó szolgáltatás nincs a modulban.

## Konfiguráció és hibakezelés

A `.env.example` az összes `MATCHING_*` változót felsorolja. A táblanévnek
a fájlsémában szerepelnie kell. Alapkorlát: 100 jelölt, 1000 vizsgált sor,
3000 ms statement/lock timeout, 5 másodperc kapcsolati timeout, 1000 karakteres mező.
Minden súly pozitív és legfeljebb 100. A sorrend:
`0 < duplicate < likely < exact <= 1`; a modellkorlát és a margin kisebb a likely
küszöbnél; a sorlimit legalább a jelöltlimit. Érvénytelen konfiguráció hibát ad.

A napló csak státuszt, darabszámot, szakaszt és kivételtípust tartalmaz.
SQL-paraméter, dokumentumszöveg, DSN, jelszó vagy nyers driverhiba nem kerül bele.
A keresési metadata megőrzi a sémát, scope-ot, korlátokat és részlegességet.
A processing metadata külön méri a keresést, pontozást és teljes időt,
és azonosítja a konfigurációt egy lenyomattal. A mérési idők természetesen
futásonként változnak; a döntés és rendezés determinisztikus.

## Streamlit használat és munkamenet

```powershell
venv\Scripts\python -m streamlit run app/web/simple_server.py
```

1. Nyisd meg a **Dokumentum elemzése – PDF / DOCX** panelt.
2. Tölts fel dokumentumot, majd kattints az **Analyze document** gombra.
3. Ellenőrizd a Document type, Mapped fields, Unmapped fields és Validation issues
   részeket. Az egyeztetés a már elkészült eredményből dolgozik.
4. Kattints az **Egyeztetés az adatbázissal** gombra.
5. Ellenőrizd a státuszt, a rangsorolt jelölteket, a pontozás indokait, a
   mezőeltéréseket és a javasolt műveleteket.

A PostgreSQL-keresés csak a külön gombra indul. A munkamenet megőrzi az
egyeztetési eredményt, ezért a Streamlit szokásos újrarajzolása nem indít új
DB- vagy LLM-hívást. Új feltöltés vagy az **Analyze document** ismételt
megnyomása törli a korábbi egyeztetést. Egy sikertelen egyeztetés megőrzi az
eredeti dokumentumelemzést.

A hasonlósági pontszám algoritmikus rangsorolási érték, nem kalibrált
valószínűség. A felület minden javaslatnál megmutatja az ellenőrzési igényt.
Nincs alkalmazó vagy jóváhagyó gomb, adatbázisfrissítés és dokumentumcsatolás
nem történik. A technikai metaadatok külön debug panelen tekinthetők meg.

## Tesztelési módszertan

A tiszta üzleti logika determinisztikus tesztadatokkal és helyettesíthető
repositoryval ellenőrizhető. A Streamlit AppTest a gombvezérelt indítást,
az eredménytárolást, a hibakezelést és az új elemzéskor történő törlést vizsgálja.
A régi SQL/RAG/HYBRID és dokumentumfeldolgozási tesztek regressziós ellenőrzést
adnak. Az élő PostgreSQL-ellenőrzés és az izolált adatbázis-integráció külön
bizonyíték; a mockolt teszt önmagában egyiket sem helyettesíti.

Az offline mérés módszerét és futtatását a
[rekordegyeztetési kiértékelés](record_matching_evaluation.md) dokumentálja.
A szintetikus adatokon mért eredmények nem jelentenek üzemi pontossági garanciát.

```powershell
venv\Scripts\python -m pytest -q
venv\Scripts\python -m pytest -q --run-docling-pdf --run-matching-postgres
venv\Scripts\python -m scripts.audit_matching_schema --output evaluation/results/schema_audit.json
venv\Scripts\python -m scripts.evaluate_matching --repeats 5
```

Az integrációs teszt új, ideiglenes PostgreSQL-klasztert indít, kizárólag
127.0.0.1-en, szabad porton. Nem használ `DB_*` adatokat. A tesztadatokon végzett
DDL és írás kizárólag ebben az eldobható klaszterben történik; a teszt külön
ellenőrzi, hogy a repository read-only tranzakciója az írást elutasítja.
`MATCHING_TEST_PG_BIN` megadhatja az `initdb`/`pg_ctl` könyvtárát. Alapértelmezés
Windows alatt `C:/Program Files/PostgreSQL/18/bin`; másutt a PATH is keresett.

## Korlátok és továbbfejlesztés

- A dokumentumkinyerés és a séma szerinti mapping továbbra is tévedhet.
- A többeszközös dokumentumok teljes feldolgozásához eszközönkénti csoportosítás
  és a Docling táblázatsorainak tartós reprezentációja szükséges.
- Ellenőrzött adatbázis-egyediség nélkül egy hasonló rekord nem tekinthető
  garantáltan azonosított célnak.
- A korlátozott kandidánskeresés nem bizonyítja globálisan egy rekord hiányát.
- A pénzösszehasonlítás egyező pénznemet igényel; nincs árfolyamkonverzió.
- A javaslatok végrehajtásához külön adatmodell, tranzakciós módosítási API,
  jogosultságkezelés és auditnapló szükséges.
- A pontozási súlyok és küszöbök mérnöki szabályok; valós adatokkal végzett,
  elkülönített tanító/validáló/teszt mérés szükséges a későbbi hangolásukhoz.
