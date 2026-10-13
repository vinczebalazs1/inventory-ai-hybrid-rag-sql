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
58 szintetikus eset: 10 kalibrációs és 48 elkülönített teszteset. A végső
teszthalmaz 50 eszközsort és 115 dokumentummezőt tartalmaz, eseten belül kis
leltárakkal. Az esetekhez nem kerülnek valódi üzleti rekordok.

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
Az offline repository a tényleges `select_candidates()` függvényt alkalmazza.
A kis leltárak teljes bejárását szimulálja; PostgreSQL-querytervet és nagy
adatbázisok SQL-tokenelőszűrésének recallját nem modellezi.

## Metrikák definíciói

- **Top-1:** az első rangsorolt jelölt helyes-e. Csak ismert, létező helyes
  rekordot tartalmazó eseteken értelmezett (34 teszteset). Egy review alatt álló,
  ki nem választott kandidáns is lehet helyesen rangsorolt.
- **Matching precision/recall/F1:** a `matched_record` által javasolt kapcsolat
  rekordazonosság szerinti micro mutatói. `TP/(TP+FP)`, `TP/(TP+FN)`,
  `2TP/(2TP+FP+FN)`. Téves rekordválasztás egy FP és egy FN. A tartózkodás
  létező helyes rekord mellett FN. A többentitásos, azonosság szerint nem
  értékelhető esetek kimaradnak (46 értékelhető teszteset).
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
  P95. Nem futott szakasz ideje 0. A P95 legalább 20 mintánál értelmezett.
  Az ismétlések nem új, független adatpontok az algoritmus pontosságához.

Nulla nevező esetén a metrika JSON `null`, nem mesterséges 0 vagy 1.
A metrikafüggvények külön, kézzel számolt kis példákkal teszteltek.

## Futtatás és reprodukálhatóság

```powershell
venv\Scripts\python -m scripts.evaluate_matching --repeats 5
venv\Scripts\python -m pytest -q tests/test_matching_evaluation.py tests/test_matching_evaluation_metrics.py
```

Opcionális: `--dataset <json>` és `--output <könyvtár>`.
A `--repeats` pozitív egész. Az ismételt döntések/rangsorok egyezését a futtató
ellenőrzi; időadatokat ehhez nem hasonlít össze.

Generált fájlok:

- [matching_metrics.json](../evaluation/results/matching_metrics.json): splitenkénti
  és stratégiánkénti metrikák, baseline-különbségek, konfigurációk, adat/kód SHA-256,
  Python- és könyvtárverziók, mérési határ.
- [matching_cases.csv](../evaluation/results/matching_cases.csv): mind a 116
  eset–stratégia pár elvárt/tényleges döntése, jelöltjei, eltérései és mért ideje.

A szándékosan szimulált adatbázishiba esetén `ConnectionError` kategóriájú
naplósor várható; ez nem élő kapcsolódási próbálkozás vagy mérési hiba.
A `.env` MATCHING változói nem hangolják át a benchmarkot: explicit alapkonfigurációval fut.

## Tényleges eredmények

Futtatás: 2026-10-10, Windows, Python 3.11, RapidFuzz 3.14.6, öt ismétlés.
Az alábbiak a **48 tesztesetre** vonatkoznak. A kalibrációs eredmények külön
szerepelnek a JSON-ban, nincsenek összekeverve ezekkel.

| Metrika | Exact-only | Hybrid |
|---|---:|---:|
| Helyes javasolt kapcsolat (TP) | 18 | 24 |
| Téves kapcsolat (FP) | 0 | 0 |
| Meg nem adott helyes kapcsolat (FN) | 16 | 10 |
| Precision | 1,0000 | 1,0000 |
| Recall | 0,5294 | 0,7059 |
| F1 | 0,6923 | 0,8276 |
| Top-1 | 0,6176 | 0,8235 |
| Precision@3 | 0,2157 | 0,3039 |
| Recall@3 | 0,6471 | 0,9118 |
| Precision@5 | 0,1294 | 0,1824 |
| Recall@5 | 0,6471 | 0,9118 |
| Státuszpontosság | 0,7917 | 0,9167 |
| Művelethalmaz egyezése | 0,8125 | 0,9375 |
| Review-elvárás egyezése | 1,0000 | 1,0000 |
| Bizonytalanság miatti review felismerése | 1,0000 | 1,0000 |
| AMBIGUOUS címke recall | 0,3333 | 1,0000 |
| Review rate | 0,8125 | 0,8125 |
| Tartózkodás | 0,6250 | 0,5000 |
| Téves automatikus egyezés | 0 | 0 |
| Hibás újrekord-javaslat | 0 | 0 |
| Delta TP / FP / FN | 6 / 0 / 4 | 8 / 0 / 2 |
| Delta precision / recall / F1 | 1,0000 / 0,6000 / 0,7500 | 1,0000 / 0,8000 / 0,8889 |

A hibrid recall javulása ezen a halmazon 17,65 százalékpont, az F1 különbsége
0,1353. Ez a kis szintetikus adatkészletre vonatkozó megfigyelés.
A hibrid több munkát végez és lassabb; sebességelőnyt nem mutatott a mérés.

| Szakasz, ms | Exact átlag / medián / P95 | Hybrid átlag / medián / P95 |
|---|---:|---:|
| Memóriabeli kandidánskeresés | 0,0461 / 0,0455 / 0,1125 | 0,0741 / 0,0744 / 0,1225 |
| Pontozás | 0,1037 / 0,0231 / 0,3549 | 0,1914 / 0,2008 / 0,4344 |
| Teljes egyeztetés | 0,4703 / 0,3934 / 0,9146 | 0,6248 / 0,6369 / 1,0949 |

240 időminta/stratégia/szakasz. A leltáradatok mérete nagyon kicsi; ebből
üzemi PostgreSQL-latencia vagy nagyságrendi skálázhatóság nem következik.

## A referenciától eltérő döntések

Nem írtuk át utólag a kézi címkéket a pontszámok javítása érdekében.

| Eset | Referencia és tényleges különbség |
|---|---|
| T06 | Pénzkülönbséget vár, de nem ad pénznemet. Az implementáció NOT_COMPARABLE-t és review-t ad, pénzfrissítést nem javasol. |
| T10, T12 | Modellnév-konfliktusra CONFLICTING_DATA-t vár. Pontos azonosító nélkül a matcher NO_MATCH + review-t ad, a modellkonfliktust a jelöltnél jelzi. |
| T29 | Hibás azonosító mellett INSUFFICIENT_DATA-t vár. A valid név alapján LIKELY + review keletkezik; csatolás/frissítés nincs. |
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
