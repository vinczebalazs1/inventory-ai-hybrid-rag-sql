# Reprodukálható szintetikus leltár

## Hivatalos készlet

Verzió: 1.0, seed: 42, 1000 fizikai eszköz, `L-00001`–`L-01000`.
Minden mező szintetikus, nincs személyes adat, jelszó vagy átmásolt üzleti rekord.

```powershell
venv\Scripts\python -m scripts.generate_inventory_data --seed 42 --count 1000 --output data/synthetic --documents
```

A `--documents` elhagyható, ha csak CSV/JSON és manifest szükséges. A generálás
mindig validál; nincs ellenőrzést kikapcsoló kapcsoló. Nem igényel PostgreSQL-t,
OpenAI-t, Qdrantot vagy internetet. A dokumentumokhoz a requirements-dev.txt
python-docx és ReportLab függőségei szükségesek.

| Kategória | Darab |
|---|---:|
| Laptop | 300 |
| Asztali gép | 200 |
| Monitor | 200 |
| Nyomtató | 100 |
| Switch | 40 |
| Router | 30 |
| Egyéb hálózati eszköz | 30 |
| Projektor | 40 |
| Szerver | 30 |
| Egyéb irodai IT | 30 |
| **Összesen** | **1000** |

26 rögzített modell és cikkszám szerepel. Mindegyik többször fordul elő.
A Dell Latitude 5540 és 5550 egyaránt 60 eszközt jelent, külön leltári számokkal.
Ezért a típusnév önmagában nem fizikai eszközazonosság.

Helyszínek: NIK 199, KGK 209, LIB 209, BARK 196, KANDÓ 187. Minden modell több
helyszínen szerepel; a helyszín nem a modellből következik.

## Generálási algoritmus

1. `GenerationConfig`: szigorú seed/count/locations szerződés, maximum 100 000 sor.
2. A darabszámot a rögzített kategóriaarányok alapján, legnagyobb maradék módszerrel
   osztjuk el. Egyenlő maradék esetén a katalógus rögzített sorrendje dönt.
3. Kategórián belül a modellek ciklikusan ismétlődnek. A cikkszám, név, ársáv,
   megengedett kezdeti dátum és élettartam egy `Product` bejegyzésből származik.
4. Saját `random.Random(seed)` példány választ dátumot, árat és helyszínt.
   Nem használunk globális RNG-t, élő órát, LLM-et vagy Faker-neveket.
5. A leltári szám a sorszámból képződik. `item_code` terméktípus, `sub_code=0`,
   `quantity=1`. Egyetlen név/cikkszám sem kap véletlenszerűen más kategória árát.
6. Minden dátum 2020-01-01 és 2026-09-30 között van; az újabb modellekhez a
   katalógus ennél későbbi szintetikus jogosultsági kezdődátumot rendel.
   Ezek tesztelési feltevések, nem gyártói megjelenési dátumokra tett állítások.

Pénzügyi modell: egész HUF, katalógusonkénti szintetikus ársáv, 1000 Ft-os lépések.
Az árak nem piaci árajánlatok. A referenciaidőpont mindig **2026-09-30**.

```text
age_days = reference_date - activation_date
depreciation = purchase_value * min(age_days, useful_life_days) // useful_life_days
current_value = purchase_value - depreciation
```

Nincs float-kerekítés. A depreciation felhalmozott értékcsökkenés, legfeljebb a
beszerzési érték. A hasznos élettartam kategória/modell szerinti, 1825–2920 nap.
Ez determinisztikus tesztmodell, nem jogszabályi/számviteli állásfoglalás.

## Export és manifest

- [inventory.json](../data/synthetic/inventory.json): kanonikus UTF-8 JSON,
  kulcsok rendezve, leltári szám szerinti sorrend, LF sorvég.
- [inventory.csv](../data/synthetic/inventory.csv): ugyanazok a rekordok, a meglévő
  11 mező sorrendjében. Az importer az integer oszlopokat explicit konvertálja;
  a leltári számot szövegként őrzi meg.
- [manifest.json](../data/synthetic/manifest.json): verziók, seed, darabszám,
  konfiguráció, rögzített generálási feltevések, UTC keletkezési idő, hash-ek,
  minőségi összesítés és a dokumentumcsomag hivatkozása.
- [ground_truth.json](../data/synthetic/ground_truth.json): 16 eset ismert mezői,
  eredeti formázása, várt azonossága, különbségei, kategóriája, javaslatai,
  review-igénye és a 32 dokumentum fájlonkénti hash-e.

A `canonical_dataset_sha256` csak a kanonikus rekordokat tartalmazza, timestampet
nem. A `schema_sha256` a séma JSON-tartalmából képződik, ezért független a fájl
behúzásától és Windows/Linux sorvégektől. A `.gitattributes` megőrzi a dataset
CSV/JSON LF sorvégeit. A PDF `invariant` módban, beágyazott magyar karakteres
Vera betűkészlettel készül; a DOCX ZIP időpontjai és metaadatai rögzítettek.
A manifest tárolja a python-docx/ReportLab verzióját is.

Hivatalos adathash:

```text
3a990307ca2e38916cfad1eb3410b3da7609bedcc98e3f43d0717903cdb4982a
```

A `read_bundle()` a CSV/JSON egyezőségét, minden szabályt, a fájlhash-eket,
a sémahash-t és a seedből újragenerált adatok egyezését is ellenőrzi.
A fájlonkénti 100 MB limit és a konfigurált rekordkorlát határolja a beolvasást.
A manifest nem digitális aláírás; reprodukcióra és véletlen eltérés kimutatására való.

## Dokumentumok és független referencia

Minden D01–D16 esethez egy valódi PDF és egy valódi DOCX tartozik.
Mind magyar címkéket használ, és egyértelműen szintetikus tesztadatlapként jelölt.

| Eset | Szándék |
|---|---|
| D01 | Minden mező egyezik |
| D02 | Ugyanaz a leltári szám, más helyszín |
| D03 | Eltérő aktiválási dátum |
| D04 | Eltérő beszerzési és jelenlegi érték, azonos HUF |
| D05 | Hiányzó leltári szám, ismétlődő modell és cikkszám |
| D06 | Létező leltári szám mellett hibás cikkszám |
| D07 | Névben elírás, változatlan azonosító és modellszám |
| D08 | Új Zebra ZD421, nem létező L-90001 |
| D09 | A D01-ével azonos típus másik fizikai példánya, L-00006 |
| D10 | Csak helyszín és darabszám, azonosításra elégtelen |
| D11 | Közös cikkszám és alszám, több jelölt |
| D12 | Latitude 5540 leltári száma mellett Latitude 5550 modell |
| D13 | Pontos dátum/szám/pénznem magyar formázással |
| D14 | Hibás dátum, egyébként pontos azonosító |
| D15 | Két eltérő leltári számú eszköz; tilos automatikusan összevonni |
| D16 | Magyar ékezetes címkék és KANDÓ helyszín |

Az elvárások a kiinduló rekordokból és a szándékosan szerkesztett mezőkből
készülnek a `documents.scenarios()` függvényben. Ez a modul nem importálja és
nem hívja az egyeztetőt. Az értékelt kimenetek külön riportba kerülnek; a referencia
nem alakul át automatikusan az alkalmazás válaszára.

Két ismert kategóriaeltérést a jelenlegi matcherrel megtartottunk; a részletes
[mérési útmutató](clean_inventory_testing.md) megmagyarázza őket.

## Egyéb méret és helyszínek

```powershell
venv\Scripts\python -m scripts.generate_inventory_data --seed 7 --count 10000 --output data/experiment_10000 --locations NIK KGK LIB
```

Ez kísérleti készlet. A betöltő/verifier alapból 1000 rekordot vár; kísérleti
készletnél explicit `--expected-count 10000` kell. Meglévő 1000 soros célra ezt
nem lehet ráseedelni. A 16 esetes hivatalos dokumentumcsomag legalább 1000 sort
és KANDÓ helyszínt kér; az eltérő helyszínes kísérletnél hagyd el a `--documents`-et.
