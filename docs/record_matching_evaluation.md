# Rekordegyeztetés: offline kiértékelés

## Cél és mérési határ

A mérés ugyanazon strukturált dokumentumadatokon hasonlítja össze az
`exact_only` és `hybrid` determinisztikus egyeztetést. A tényleges
`reconcile_document()` szolgáltatást, előkészítést, pontozást, összehasonlítást
és javaslatkészítést futtatja. A repository memóriában helyettesített.

Ez a mérés nem értékeli a Docling vagy az LLM adatkinyerési pontosságát, és
nem méri a hálózat, PostgreSQL vagy dokumentumfeldolgozás idejét. Ezeket a
rekordegyeztetés eredményétől külön kell mérni. A valódi PostgreSQL-hozzáférést
külön integrációs tesztek ellenőrzik.

## Adatkészlet és kézi referencia

Fájl: [matching_evaluation.json](../tests/fixtures/matching_evaluation.json).
2-es adatkészlet-verzió: **74 szintetikus eset**, 10 kalibrációs és 64 teszteset.
A korábbi 58 eset és referencia megmaradt; 16 új leltáriszám-eset került melléjük.
A teszthalmaz 5166 eszközsort és 148 dokumentummezőt tartalmaz, köztük egy
4000 soros, közös cikkszámos leltárat és egy 1100 soros részleges keresést.
Az esetekhez nem kerültek valódi üzleti rekordok.

Minden eset tartalmazza:

- dokumentummezők, eredeti/normalizált érték, opcionális címke, evidence és hibajelzés;
- kandidánsleltár a mezőértékekkel;
- a szintetikus adatbázis deklarált UNIQUE kulcsai és opcionális típuseltérései;
- teljes/részleges/timeout/hiba/sémaeltérés forgatókönyv;
- kézzel megadott helyes rekordazonosság, elvárt státusz és műveletek;
- elvárt review, bizonytalansági címke és rekordhoz kötött mezőeltérések.

A fixture `record_id` kizárólag mérési azonosító. Nem kerül át új üzleti
azonosítóként a matcherbe. A matcher kulcsai a deklarált adatbázis-egyediségből
származnak. Nincs kitalált PRIMARY KEY az egyediség nélküli esetekben.

Az eseteket és a címkéket fejlesztői munkában, az első kiértékelés előtt
állítottuk össze. Nem független, több annotátor által ellenőrzött üzemi referencia.
Az `_build_fixture.py` megőrzi a kézi szerzői definíciót; a futtató a rögzített
JSON-t olvassa, nem az aktuális matcher kimenetéből gyárt elvárt válaszokat.
Az algoritmus súlyait nem optimalizáltuk a végső teszthalmazon. A későbbi
hangolás külön kalibrációs adatokon történjen, új, érintetlen teszthalmazzal.

A referencia státusz- és műveletcímkéi néhány esetben eltérő döntési szabályt
várnak, mint a végleges, konzervatív implementáció. Ezeket megtartottuk és
alább tételesen jelentjük. A státuszpontosság ezért részben a döntési szabályok
egyezését méri; nem tekinthető tisztán rekordazonosítási pontosságnak.

## Algoritmusok

**Exact-only:** jelöltkeresés pontos `inventory_number`/`item_code` alapján.
Az összetett azonosító kulcsrészeit és a biztonsági vétókat ellenőrzi. Név
alapján nem keres új jelöltet. Az exact keresés eredménytelensége nem alapoz
meg új rekordot, mert a névalapú duplikációellenőrzés nem történt meg.

**Hybrid:** pontos azonosítók, összetett mezők, teljes névre számolt
RapidFuzz-hasonlóság, súlyozás, modellszám-vétó, margin és emberi ellenőrzés.
A részletes képlet és az alapértékek a
[moduldokumentációban](record_reconciliation.md#pontozás-és-döntési-szabályok) vannak.

A két stratégia ugyanazt a szolgáltatást és javaslatmotort használja.
Az offline repository a tényleges `InventoryRepository._search()` vezérlését
és a `select_candidates()` függvényt alkalmazza; csak a sorok SQL-olvasása
helyettesített. Így a leltári szám elsőbbsége, a másodlagos kulcs, a kihagyott
fuzzy lépés és a limitek ugyanabban a kódban dőlnek el. PostgreSQL-querytervet,
indexhasználatot és teljes SQL-tokenelőszűrési recallt ez a mérés nem modellez.

## Metrikák definíciói

- **Top-1:** az első rangsorolt jelölt helyes-e. Csak ismert, létező helyes
  rekordot tartalmazó eseteken értelmezett (47 teszteset). Egy review alatt álló,
  ki nem választott kandidáns is lehet helyesen rangsorolt.
- **Matching precision/recall/F1:** a `matched_record` által javasolt kapcsolat
  rekordazonosság szerinti micro mutatói. `TP/(TP+FP)`, `TP/(TP+FN)`,
  `2TP/(2TP+FP+FN)`. Téves rekordválasztás egy FP és egy FN. A tartózkodás
  létező helyes rekord mellett FN. A többentitásos, azonosság szerint nem
  értékelhető esetek kimaradnak (62 értékelhető teszteset).
- **Precision@K:** a helyes rekordok száma az első K helyen, osztva K-val,
  majd esetszintű átlag. Rövid listán is K a nevező. **Recall@K:** a megtalált
  helyes rekordok aránya az összes helyeshez, esetszintű átlag. K = 1, 3, 5.
- **Státusz-/műveletpontosság:** a címke, illetve a művelettípusok halmaza
  egyezik-e a kézi referenciával. A JSON státusz-confusion táblát is tartalmaz.
- **Bizonytalanság felismerése:** a kézzel bizonytalannak jelölt esetek közül
  hány kér review-t. A külön `ambiguity_status_recall` a konkrét
  AMBIGUOUS_MATCH címke felismerését méri.
- **Review rate:** az összes eset közül a review-t igénylők aránya.
  **Abstention rate:** ahol nincs kiválasztott rekord. Ez két külön mutató:
  egy LIKELY jelölt kiválasztható, miközben review szükséges.
- **Téves automatikus egyezés:** hibás kiválasztás `review_required=False`
  mellett. Itt az automatikus a döntés ellenőrzési igényére vonatkozik;
  adatbázis-művelet semmilyen esetben nem fut.
- **Hibás létrehozási javaslat:** CREATE javaslat létező helyes rekord mellett,
  vagy amikor a kézi referencia egyéb okból nem enged létrehozást.
- **Delta precision/recall/F1:** a `(helyes rekord, mező)` párok halmaza;
  csak DIFFERENT státusz. Ugyanaz a mező rossz rekordon FP és FN, az ismételt
  evidence nem többszörözi a mezőeltérést. NULL nem tekinthető bizonyított változásnak.
- **Idő:** keresés, pontozás, teljes szolgáltatás; átlag, medián, nearest-rank
  P95. Külön mérjük az elsődleges, másodlagos és fuzzy keresést. Ezek csak
  ténylegesen elindított szakaszokra adnak mintát; a teljes szolgáltatási időkben
  a nem futott szakasz 0. A P95 legalább 20 mintánál értelmezett.
  Az ismétlések nem új, független adatpontok az algoritmus pontosságához.

Nulla nevező esetén a metrika JSON `null`, nem mesterséges 0 vagy 1.
A metrikafüggvények külön, kézzel számolt kis példákkal teszteltek.

## Futtatás és reprodukálhatóság

```powershell
venv\Scripts\python -m scripts.evaluate_matching --repeats 5
venv\Scripts\python -m scripts.verify_matching_report
venv\Scripts\python -m pytest -q tests/test_matching_evaluation.py tests/test_matching_evaluation_metrics.py
```

Opcionális: `--dataset <json>` és `--output <könyvtár>`.
A `--repeats` pozitív egész. Az ismételt döntések/rangsorok egyezését a futtató
ellenőrzi; időadatokat ehhez nem hasonlít össze.

Generált fájlok:

- [matching_metrics.json](../evaluation/results/matching_metrics.json): splitenkénti
  és stratégiánkénti metrikák, baseline-különbségek, konfigurációk, adat/kód SHA-256,
  Python- és könyvtárverziók, mérési határ.
- [matching_cases.csv](../evaluation/results/matching_cases.csv): mind a 148
  eset–stratégia pár elvárt/tényleges döntése, jelöltjei, eltérései és mért ideje.

A szándékosan szimulált adatbázishiba esetén `ConnectionError` kategóriájú
naplósor várható; ez nem élő kapcsolódási próbálkozás vagy mérési hiba.
A `.env` MATCHING változói nem hangolják át a benchmarkot: explicit alapkonfigurációval fut.
A riport UTC-időbélyeget, adatkészlet-verziót, külön adatkészlet-hash-t és az
`app/`, `scripts/`, `config/`, `migrations/` fájljaira lebontott forrásmanifestet
tartalmaz. A lenyomat a tényleges fájlbájtokra vonatkozik; sorvégváltás után is
új mérés szükséges. A hash-ellenőrzés nem helyettesíti a referencia szakmai ellenőrzését.

## Tényleges eredmények

Futtatás: **2026-10-17**, Windows, Python 3.11, RapidFuzz 3.14.6, öt ismétlés.
Az alábbiak a **64 tesztesetre** vonatkoznak. A kalibrációs eredmények külön
szerepelnek a JSON-ban, nincsenek összekeverve ezekkel.

| Metrika | Exact-only | Hybrid |
|---|---:|---:|
| Helyes javasolt kapcsolat (TP) | 25 | 31 |
| Téves kapcsolat (FP) | 0 | 0 |
| Meg nem adott helyes kapcsolat (FN) | 22 | 16 |
| Precision | 1,0000 | 1,0000 |
| Recall | 0,5319 | 0,6596 |
| F1 | 0,6944 | 0,7949 |
| Top-1 | 0,6383 | 0,8085 |
| Precision@3 | 0,2199 | 0,2908 |
| Recall@3 | 0,6596 | 0,8723 |
| Precision@5 | 0,1319 | 0,1745 |
| Recall@5 | 0,6596 | 0,8723 |
| Státuszpontosság | 0,7813 | 0,9375 |
| Művelethalmaz egyezése | 0,8438 | 0,9531 |
| Review-elvárás egyezése | 1,0000 | 1,0000 |
| Bizonytalanság miatti review felismerése | 1,0000 | 1,0000 |
| AMBIGUOUS címke recall | 0,5000 | 1,0000 |
| Review rate | 0,7969 | 0,7969 |
| Tartózkodás | 0,6094 | 0,5156 |
| Téves automatikus egyezés | 0 | 0 |
| Hibás újrekord-javaslat | 0 | 0 |
| Delta TP / FP / FN | 8 / 0 / 5 | 11 / 0 / 2 |
| Delta precision / recall / F1 | 1,0000 / 0,6154 / 0,7619 | 1,0000 / 0,8462 / 0,9167 |

A hibrid recall előnye ezen a halmazon 12,77 százalékpont, az F1 különbsége
0,1004. A hibrid a névkeresés és további pontozás miatt összességében több munkát
végez. Ez nem az algoritmusváltozás előtti és utáni pontosság összehasonlítása:
a két aktuális stratégia azonos adatokon végzett mérése. A régi, 48 esetből álló
halmaz eredményét nem szabad közvetlenül az új 64 esetes eredménnyel összevonni.

Külön riportált kulcsállapotok a teszthalmazon:

| Leltáriszám-UNIQUE | Eset | Exact recall / F1 | Hybrid recall / F1 | Review (mindkettő) |
|---|---:|---:|---:|---:|
| Van | 12 | 0,5556 / 0,7143 | 0,7778 / 0,8750 | 0,6667 |
| Nincs | 52 | 0,5263 / 0,6897 | 0,6316 / 0,7742 | 0,8269 |

A második csoportban lehet igazolt másodlagos kulcs; a bontás kifejezetten
az elsődleges leltári szám egyediségére vonatkozik. Mindkét csoportban 1,0 precision
és 0 megfigyelt téves kapcsolat volt. Az összes adatbázis-kulcs nélküli eseteket
az adatkészlet üres `unique_keys` mezője külön azonosítja.

| Szakasz, ms | Exact átlag / medián / P95 | Hybrid átlag / medián / P95 |
|---|---:|---:|
| Memóriabeli kandidánskeresés | 0,1247 / 0,0528 / 0,1034 | 0,2905 / 0,0636 / 0,1951 |
| Pontozás | 0,1185 / 0,0306 / 0,2901 | 0,4119 / 0,1932 / 0,4227 |
| Teljes egyeztetés | 0,6391 / 0,4857 / 1,0162 | 1,0977 / 0,6592 / 1,3189 |
| Elsődleges leltári szám | 0,3649 / 0,0090 / 4,0340 | 0,3916 / 0,0089 / 4,1191 |
| Másodlagos kulcs | 0,0086 / 0,0079 / 0,0105 | 0,0086 / 0,0079 / 0,0113 |
| Fuzzy fallback | Nem fut | 0,3272 / 0,0620 / 0,1904 |

320 teljes időminta stratégiánként; 75 elsődleges és 150 másodlagos keresési minta;
a hibridnél 145 fuzzy minta. A memóriabeli szimuláció nem használ valódi SQL-indexet,
ezért a nagy fixture elsődleges keresési ideje sem PostgreSQL-indexlatencia.
Eltérő méretű eseteket összesítünk: egy ritka, lassú eset miatt az átlag a P95 fölé kerülhet.

### Izolált PostgreSQL: a keresési idő változása

Külön, frissen futtatott [időmérési riport](../evaluation/results/inventory_search_benchmark.json):
4000 Printer, közös cikkszám, egyedi leltári szám; 1-es jelöltlimit, 1000-es sorlimit.
5 bemelegítés, majd 50 váltakozó mérés; közös read-only kapcsolat/pillanatkép.
A kapcsolatnyitás és sémaaudit egyik mód időmérésében sem szerepel.

| Keresési szakasz | Átlag ms | Medián ms | P95 ms | Eredmény |
|---|---:|---:|---:|---|
| Korábbi OR lekérdezés, az eredeti limitvizsgálattal | 2,4107 | 2,3957 | 2,6757 | Limit miatt részleges |
| Új elsődleges leltáriszám-keresés | 0,5777 | 0,5849 | 0,6887 | 1 találat, célzott keresés teljes |
| Fuzzy fallback | 37,9985 | 37,7366 | 40,8384 | Részleges, 1003 klienshez lekért sor |

Az elsődleges keresés átlagosan 1,8331 ms-mal rövidebb volt a korábbi OR
lekérdezésnél. A régi lekérdezési szakaszt rekonstruáltuk, nem a teljes korábbi
alkalmazást futtattuk újra. A fuzzy fallback más feladatot végez; annak ideje
nem közvetlen sebességverseny. Az izolált mérésből üzemi terhelésre nem következik garancia.

Újrafuttatás és riportmentés:

```powershell
$env:MATCHING_BENCHMARK_OUTPUT = "evaluation/results/inventory_search_benchmark.json"
venv\Scripts\python -m pytest -q tests/test_matching_postgres.py -k isolated_inventory_search_benchmark --run-matching-postgres
```

## A referenciától eltérő döntések

Nem írtuk át utólag a kézi címkéket a pontszámok javítása érdekében.

| Eset | Referencia és tényleges különbség |
|---|---|
| T06 | Pénzkülönbséget vár, de nem ad pénznemet. Az implementáció NOT_COMPARABLE-t és review-t ad, pénzfrissítést nem javasol. |
| T10, T12 | Modellnév-konfliktusra CONFLICTING_DATA-t vár. Pontos azonosító nélkül a matcher NO_MATCH + review-t ad, a modellkonfliktust a jelöltnél jelzi. |
| T29 | Hibás azonosító mellett INSUFFICIENT_DATA-t vár. Az új biztonsági szabály CONFLICTING_DATA + review-t ad; a hibás azonosítót nem hagyja figyelmen kívül. |
| T30, T33 | A referencia részben hibás/üres adat mellett is csatolást vár. A szigorúbb implementáció csak review-t javasol. |
| T31 | Hiányzó evidence mellett INSUFFICIENT_DATA-t vár. A tényszerű egyedi kulcsegyezés EXACT marad, de kötelező review és csatolási tiltás mellett. |
| T44 | Eltérő pénznemű összegekhez is deltat vár. A pénzmező NOT_COMPARABLE; a helyszín, mennyiség és pénznem eltérése megmarad. |

A T06 és T44 eltéréseket a jelenlegi referenciához számolt delta-recall
beleszámolja FN-ként. Emiatt az összesített delta-mutatót a döntési szabályok
ismeretében kell értelmezni. Új benchmarkverzió előtt ezek a referenciák külön,
független szakmai felülvizsgálatot igényelnek; itt nem rejtettük el őket.

## Érvényességi korlátok és következő mérések

- A dokumentummezők és az azonosságok szintetikusak; a tervezői elfogultság valós kockázat.
- A típus-, márka- és nyelveloszlás nem reprezentatív vállalati minta.
- 0 megfigyelt téves automatikus kapcsolat nem bizonyít 0 üzemi hibaarányt.
- A tartózkodásból eredő FN sokszor tudatos biztonsági döntés; a recall önmagában nem elég.
- A névmodell digitális tokeneket ellenőriz, nem teljes terméktaxonómiát vagy fizikai eszközazonosságot.
- A tényleges üzleti táblában nincs igazolt kulcs; a szintetikus UNIQUE példák nem változtatnak ezen.
- A teljes PDF/DOCX → mezőkinyerés minőségét valós dokumentumok kézi referenciájával külön kell mérni.
- Üzemi DB-n reprezentatív volumen, indexek, lekérdezési terv, p95/p99 és többfelhasználós terhelés külön vizsgálatot igényel.
- A további algoritmusváltozatok értékeléséhez új, független teszthalmaz szükséges; a mostani készlet már ismert a fejlesztés számára.
