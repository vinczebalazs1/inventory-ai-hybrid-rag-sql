# InventoryAI – dokumentumfeldolgozás és rekordegyeztetés stabilizálása

**Dátum:** 2026-11-14. **Kiinduló HEAD:** `a7bd4278aaa4a7da6aa7375ff1741c6e9107ab83`, `main`. A munkakönyvtár már a feladat előtt módosított volt; ezeket megőriztem. Az alábbi változáslista a feladat eleji fájlhash-ekhez viszonyított, nem a teljes Git diff.

## A. Megvalósítás és fájlok

A folyamat továbbra is Docling → LLM-kinyerés → mezőmegfeleltetés → normalizálás → egyeztetés. Az egyeztetés most először forrásbizonyíték alapján eszközcsoportokat képez, majd külön-külön keres és hasonlít. Nincs adatbázisba visszaíró művelet.

| Fájlok | Változás oka és tartalma |
|---|---|
| `app/document_processing/models.py`, `docling_parser.py` | Előfordulásazonosító, eredet, normalizálási állapot, OCR-cella, tényleges koordináta és felismerési pontszám megőrzése. A parser köztes cellái megmaradnak; nem kapcsoltunk be teljes oldalas kényszer-OCR-t. |
| Új `app/document_processing/provenance.py`; `extraction_service.py` | Ellenőrzött forrásrészletek és tényleges előfordulások. Oldalak közötti ismétlések megőrzése; chunkátfedés duplikátumainak kiszűrése. A `0` nem kaphat hamis előfordulást egy másik szám belsejében. Az LLM által küldött koordináták/bizonyossági számok nem használhatók parserbizonyítékként. |
| Új `app/document_processing/field_labels.py`; `field_mapper.py`; `app/prompts/document_extraction.txt` | Pontos magyar/angol címkealiasok, kontextus és kinyerési bizonytalanság megőrzése. A modell nem tölthet ki hiányzó adatot vagy cserélhet OCR-karaktert feltételezésből. |
| `app/document_processing/validation_service.py` | `db`/`darab`, Ft/HUF, négyféle szóköz, Unicode mínusz, magyar dátumformátum. Szigorú számcsoportosítás; nulla és negatív érték megőrzése. Hiányzó, ismeretlen, érvénytelen és nem értelmezhető értékek külön állapota. |
| Új `app/record_matching/grouping.py`; `preparation.py` | Külön fizikai leltári azonosítók szerinti csoportok; csak igazolt kártya/sor/oldalkapcsolat alapján rendelt mezők. Belső ellentmondás nem lesz második eszköz. Pénzügyi összefüggés ellenőrzése pontos Decimal-számítással, csoportonként. |
| `app/record_matching/repository.py`, `candidate_service.py` | Pontos, igazoltan egyedi leltáriszám-találat megtartása cikkszámkonfliktus mellett is. SQL-ben rangsorolás a LIMIT előtt; korlátozott lekérdezések és külön teljességi jelzések. |
| `app/record_matching/normalization.py`, `matching_engine.py` | Névmezőnél szóközeltérés tolerálása, azonosítók karakterhű kezelése. Konfliktus miatt nem nullázódik minden jelölt pontszáma. Az elsődleges találat és az elfogadhatóság külön információ. |
| `app/record_matching/models.py`, `comparison_service.py`, `reconciliation_service.py`, `suggestion_engine.py` | Csoportonkénti eredmények; `identified_record`, `critical_conflict_fields`, `unassigned_fields`, `counts`; külön `INTERNAL_CONFLICT` és `UNCERTAIN` összehasonlítás. Frissítési javaslatban eredeti/normalizált/DB-érték és bizonyíték. Minden művelet továbbra is `executable=false`. |
| `app/web/document_preview.py`, `reconciliation_preview.py`; új `document_exports.py` | Csoportok, konfliktusok, validáció, előfordulás- és egyedi mezőszámlálás. Azonos eredményobjektumból készülő CSV-k, táblázatképlet elleni védelemmel. A feltöltés és az egyeztető gomb megmaradt. |
| `app/evaluation/runner.py` | A szimulált lekérdezés követi a jelöltrangsorolást; determinisztikusság-ellenőrzés a beágyazott csoportok futásidejét is elkülöníti. Referenciaeredményt nem írtunk át. |
| Új `tests/test_document_stabilization.py`, `test_stabilization_pdf.py`, `test_stabilization_postgres.py` | T01–T15 referenciaesetek, negatív esetek, Streamlit/JSON/CSV, valódi helyi PDF/OCR és izolált SQL-rangsorolás. |
| `tests/test_detailed_single_asset.py`, `test_document_processing.py`, `test_financial_normalization.py`, `test_inventory_identity.py`, `test_record_repository.py` | A megváltozott követelmények ellenőrzése: ismétlések megtartása, HUF támogatása, belső konfliktus külön kezelése, elsődleges találat és paraméterezett SQL. |
| `tests/test_matching_postgres.py`, `test_inventory_clean_integration.py`, `test_inventory_scalability.py` | Az ideiglenes tesztklaszter kapcsolatán explicit írható **teszt-előkészítés**, hogy a fejlesztői `PGOPTIONS` írásvédelme ne akadályozza a fixture létrehozását. Az alkalmazás repositoryja továbbra is read-only tranzakciót nyit; ezt külön teszt ellenőrzi. |

A régi mérési riportok, a referencia-JSON-ok, a dokumentumok, a konfigurációk, `.env` és függőségek nem változtak. A SQL/RAG/HYBRID alkalmazáskódhoz ebben a feladatban nem nyúltam.

## B. Javított hibakategóriák

1. **Csoportosítás:** az előfordulások megmaradnak. Azonos leltári szám több oldalon egy csoport; különböző fizikai azonosítók külön csoportok.
2. **Több eszköz:** csoportonként külön keresés és összehasonlítás. Bizonytalan hozzárendelés látható és blokkolja az elfogadási javaslatot; nincs legközelebbi érték alapján találgatás.
3. **Rekordkeresés:** az elsődleges lookup független a másodlagos találatok számától. A tényleges clean séma kompatibilis; teljes egyedi kulcs: `inventory_number`.
4. **Rangsorolás:** megőrzött relevanciapontszám és indoklás konfliktus mellett; elsődleges ID prioritása, további mezőegyezések szerinti sorrend. A score továbbra sem valószínűség.
5. **Számok:** `0`, `1 db`, `1db`, `darab`, Ft/HUF, U+0020/U+00A0/U+202F/U+2009 és `−` támogatott. Hibás csoportosítás, kétértelmű `1,234`, OCR-es `5O0` nem javítódik automatikusan.
6. **Hiány/érvénytelenség:** a `nem ismert`, üres/NULL, hibás dátum és értelmezhetetlen szám eltérő állapot. Egy hibás előfordulás nem teszi hibássá a többi azonos nevű mezőt.
7. **Kritikus konfliktus:** a pontos leltáriszám-találat megmarad, miközben az eltérő cikkszám/modell megakadályozza a konfliktusmentes elfogadást.
8. **Eltérésszámlálás:** előfordulások és egyedi mezők külön; több csoportnál az egyedi **csoport–mező** eltérések összege szerepel.
9. **OCR:** helyi Docling/RapidOCR. Csak a parser tényleges felismerési pontszáma használható; 0,95 alatti vagy nem egyértelműen hozzárendelhető cella bizonytalan. A magas OCR-pontszám sem hitelesít önmagában DB-től eltérő értéket: képellenőrzésig `UNCERTAIN`, nem rekordfrissítés.
10. **Döntéstámogatás:** belső ellentmondás, bizonytalan OCR, hiányos hozzárendelés vagy hibás pénzügyi összefüggés esetén emberi ellenőrzés. Nincs abszolútérték-képzés, DB-ből kitalált dokumentumérték vagy automatikus rekordírás.

## C. Tényleges teszteredmények

**Végleges teljes futás: 515 sikeres, 0 sikertelen, 0 error, 0 kihagyott teszt, 272,37 másodperc.** A 14 figyelmeztetés a Docling/RapidOCR meglévő elavuló API-jaihoz tartozik. A kiinduló tesztkör: 344 sikeres, 84 kihagyott.

Bizonyíték: [JUnit](../evaluation/stabilization_2026-11-14/test_results.xml), [végellenőrzés](../evaluation/stabilization_2026-11-14/verification.json), [167 fájlos forrás-/tesztmanifest és csomaglista](../evaluation/stabilization_2026-11-14/source_environment.json). A futás előtti és utáni forrás-/teszthash-ek **167/167 egyeznek**. A korábbi, köztes sikertelen futások hibáit javítottuk; nem azokat tekintjük véglegesnek.

A következő táblázat determinisztikus, a feladatban megadott referenciaadatokra épülő teszteket jelent. Ezek **mind lefutottak** szimulált repositoryval, majd a valódi `inventory_ai_clean` read-only repositoryval is. Az utóbbi nem használ LLM-et vagy PDF-et; a megadott mezőelőfordulásokat egyezteti. A 16 referenciarekord mindegyike egyezett a tényleges adatbázissal.

| Eset | Elvárt és tényleges viselkedés | Eredmény / hatókör |
|---|---|---|
| T01 | L-00021 pontos, 11 mező egyezik, 0 eltérés; quantity érvényes | PASS, logika + valódi read-only PG |
| T02 | L-00022, egy csoport, ismételt bizonyítékok megmaradnak, 0 eltérés | PASS, logika + PG; valódi ötoldalas PDF külön alább |
| T03 | LIB/NIK: 2 eltérő előfordulás, 1 egyedi location-eltérés, felülvizsgálandó frissítés | PASS |
| T04 | 2 pénzügyi mezőeltérés; a dokumentum kivonása helyes | PASS |
| T05 | Hiányzó leltári szám nem töltődik vissza; 1 db érvényes, nincs igazolt egyedi kapcsolás | PASS; élő készleten SEARCH_INCOMPLETE |
| T06 | Ismeretlen dátum, alszám=0 megmarad; pontos ID és ellenőrzés | PASS |
| T07 | −171294 megmarad, 1 eltérés, pénzügyi összefüggés figyelmeztetése | PASS |
| T08 | 2025-13-40 érvénytelen marad, de L-00028 azonosítása működik | PASS |
| T09 | Magyar szám- és dátumformátum, 0 eltérés | PASS |
| T10 | L-0003O nem lesz L-00030; releváns jelölt, emberi ellenőrzés | PASS; élő készleten SEARCH_INCOMPLETE |
| T11 | L-00031 elsődleges találat megmarad, 2 kritikus eltérés, nincs csatolási javaslat | PASS |
| T12 | L-99999 nem kapcsolódik önkényesen más rekordhoz | PASS; élő készleten SEARCH_INCOMPLETE |
| T13 | L-00033 és L-00034 külön csoport, mindkettő pontos, 0 eltérés | PASS |
| T14 | Egy csoport, KGK/NIK mindkét oldallal megmarad, 1 belső konfliktus | PASS |
| T15 | Helyes mezőbemenetnél pontos L-00036; bizonytalan OCR-bemenet nem eredményez igazolt eltérést/frissítést | PASS, logikai szerződés; **nem az eredeti T15 PDF felismerési mérése** |

### Valódi dokumentumok és a bizonyíték határa

- A repositoryban nincs meg az eredeti T01–T15 PDF/ground-truth csomag. A Letöltésekben megtalált `T02_document.pdf` öt oldalas, L-00022 / Dell Latitude 5550; a két első oldal és a pénzügyi összefüggés megfelel a megadott végleges referenciaadatnak. A feldolgozási próba valódi Doclingot és kézzel megadott, a tényleges parserkimenetben ellenőrzött LLM-válaszstubot használ.
- A T02-ben felismert „Megnevezés / Dell Latitude 5550” táblafejléc valójában mező–érték forma. A javítás ezt megkülönbözteti a valódi eszközsortáblától; a többeszközös védelem megmaradt.
- A valódi T02 végső próbája **EXACT_MATCH, 58 megőrzött és egyező előfordulás, 0 eltérés, 0 validációs probléma**, ellenőrzési kényszer nélkül. PDF SHA-256: `774f537ab0c8b1ba3b6f0db45b445f9d51629b972d9be714015d66d091476902`. [PDF/OCR-próbák összesítése](../evaluation/stabilization_2026-11-14/pdf_checks.json).
- A régi D01/D02 PDF- és DOCX-fájlokon valódi Docling-feldolgozás, stubos LLM, egyeztetés és regresszió fut. A korábbi ötlapos részletes D01 mentett valódi parserkimenetére is van regresszió.
- Készült **külön, generált, képalapú kétoldalas OCR-próba** enyhe ferdítéssel és gyengébb kontraszttal. Nincs beágyazott szövegrétege. A tényleges OCR-ben a `KANDÓ` helyett `KANDO` jelent meg, a `quantity=1` kimaradt. Ezeket nem javítottuk referenciaadatból: a próba azt ellenőrzi, hogy az eredmény ellenőrzést kér és nem javasol bizonyított frissítést. Ez **részleges felismerés, sikeres biztonsági viselkedéssel**, nem hibátlan OCR-eredmény.
- Élő LLM-/embeddinghívás és új böngészős kézi teszt nem történt. A Streamlit ellenőrzése AppTesttel futott. Az eredeti T15 nehéz szkennelt PDF pontos felismerési arányát annak hiányában nem lehet igazolni.

### Reprodukálás

```powershell
$env:STABILIZATION_T02_PDF = 'C:\Users\vincz\Downloads\T02_document.pdf'
$run = Join-Path (Get-Location) ('.cache/stabilization-repeat-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $run | Out-Null
$env:CLEAN_INVENTORY_REPORT_DIR = Join-Path $run 'clean'
$env:MATCHING_BENCHMARK_OUTPUT = Join-Path $run 'benchmark.json'
.\venv\Scripts\python.exe -X utf8 -B -m pytest -q -p no:cacheprovider --run-docling-pdf --run-matching-postgres "--junitxml=$run/tests.xml"
```

Feltételek: meglévő virtuális környezet és helyi Docling-modellek; PostgreSQL `initdb`/`pg_ctl` (a teszt alapból PostgreSQL 18 binárist keres). A PostgreSQL opt-in tesztek kizárólag külön, ideiglenes, véletlen loopback-portú klasztert hoznak létre. A termelési adatbázist nem írják. A T02 fájl hiánya célzott kihagyást eredményez.

## D. Korlátok és mérési hatókör

- A csoportosítás tudatosan konzervatív. Több azonosító és egyértelmű kártya/sor/oldalkapcsolat nélküli mezők hozzárendeletlenek maradnak. A cikkszám önmagában nem fizikai eszközazonosító.
- Hiányos másodlagos/fuzzy keresésből nem állítjuk egy rekord globális hiányát. Az azonos bizonyítékú jelöltek stabil sorrendje nem bizonyítja, melyik a helyes fizikai példány.
- A tényleges LLM-kinyerés továbbra is szolgáltatásfüggő, ezért a stubos integrációk nem élő LLM-pontosságmérések.
- A tényleges OCR nem hibátlan. Sem a küszöb, sem a magas felismerési pontszám nem általános pontossági garancia.
- Az új `MULTIPLE_ASSETS`, `INTERNAL_CONFLICT`, `UNCERTAIN` állapotokhoz a jelenlegi Streamlit fogyasztó frissült. Külső, saját eredményfeldolgozó kliensnek ezeket kezelnie kell.
- A 100 ismételt logikai oldalt / 1100 mezőelőfordulást tartalmazó helyi fixturepróba átlagosan 205,85 ms volt (5 ismétlés). Ez nem Docling-, LLM- vagy hálózati idő. 1/10 oldalnál 7,76/26,46 ms. A teljes parseradatot nem másoljuk le minden eszközcsoporthoz.
- A korábbi szakdolgozati metrikák korábbi implementációt mértek. A jelen változtatás után nem állítható, hogy a régi forrásmanifest egyezik. A régi riportokat megőriztük; az új tesztbizonyíték külön készül.

**Új mérés a változatlan, korábbi 74 esetes fixture-ön:** a 64 esetes test részhalmazban exact-only precision/recall/F1 = 1,000000 / 0,531915 / 0,694444; hybrid = 1,000000 / 0,659574 / 0,794872. Mindkettőnél 0 téves automatikus egyezés és 0 téves újrekord-javaslat. Az új top-1 értékek 0,617021 / 0,787234; ezért nem állítjuk, hogy minden régi rangsormetrika változatlan vagy javult. A CLI a szándékos adatbázishiba-fixture-höz ConnectionError naplóbejegyzést is készít; ez szimulált negatív eset, nem élő kapcsolatprobléma.

Az új clean, izolált PostgreSQL-értékelés továbbra is 14/16 referenciaegyezést ad, de most **D05 és D15** kategóriája tér el: D05 `SEARCH_INCOMPLETE` az elvárt `AMBIGUOUS_MATCH` helyett; D15 az új, tényleges többcsoportos `MULTIPLE_ASSETS` az eredeti `CONFLICTING_DATA` helyett. A reference JSON változatlan; identity/differences/actions/review ellenőrzéseik igazak. Ez nem a 15 új stabilizálási eset eredménye, hanem külön régi referenciahalmaz. A státuszeltéréseket nem fedtük el a referencia átírásával.

## E. Biztonság és bizonyítékok

Az `inventory_ai_clean` **1000 sora és sémája nem módosult**. A teljes, rendezett rekordtartalom kezdeti hash-e és a 15 valódi read-only ellenőrzés utáni hash egyezik:

```text
3109f2e0ade6a0cc6aabb675b378b1da6e52e7c5698f3bcd4948879f5d72a9aa
```

A hash előállítása: `json.dumps(rows, sort_keys=True, ensure_ascii=False, default=str)`, inventory_number szerint rendezett, összes oszlopot tartalmazó sorokból. Nem a más korábbi riportok eltérő szerializálással számolt hash-éhez hasonlítottuk.

Az alkalmazás repositoryja `readonly=True`, `REPEATABLE READ`, paraméterezett SQL, kapcsolat-/lekérdezési időkorlát és sentinel LIMIT mellett dolgozik. Az izolált PostgreSQL-teszt konkrétan ellenőrzi az írás elutasítását. Az összes javaslat nem végrehajtható; jóváhagyást követő mentési funkciót ez a modul továbbra sem biztosít.

Qdrant-műveletet nem indítottunk; az automatizált tesztek helyi, memóriabeli klienst használnak. A kiinduláskor rögzített régi riportok/adatfájlok/konfigurációk hash-e változatlan. Kulcsot és jelszót nem mentettünk.

Helyi részletes diagnosztika: `.cache/stabilization_2026-11-14/`. A végleges, megosztható bizonyítékok az új [evaluation/stabilization_2026-11-14/](../evaluation/stabilization_2026-11-14/) könyvtárban vannak: JUnit, forrás-/tesztmanifest, csomaglista, read-only referenciaesetek, PDF/OCR-összesítés, új offline és izolált PostgreSQL-mérések, teljesítménypróba, végellenőrzés és artefaktumhash-ek. A korábbi sikertelen köztes futások nem végleges teszteredmények.

## F. Végső állapot

**Implementáció: kész a dokumentált prototípus-hatókörben.**

**Automatizált tesztek: 515 sikeres / 0 sikertelen / 0 kihagyott.** A 15 kötelező referenciaeset logikai tesztként és valódi read-only PG-ellenőrzésként is lefutott. Az eredeti PDF-ek közül csak T02 állt rendelkezésre; a további **14 eredeti PDF-integráció nem igazolható**, nem szerepel sikeres eredményként. Külön sikeres D01/D02 PDF/DOCX-regresszió és önálló, generált OCR-biztonsági próba készült.

**Ismert kritikus biztonsági hiba:** a lefuttatott ellenőrzések nem tártak fel téves automatikus rekordkapcsolást vagy adatírást. A fennmaradó OCR-felismerési hibák emberi ellenőrzést igényelnek; nem állítunk hibamentes felismerést vagy minden dokumentumra garantált eredményt.

**Adatbázis-módosítás:** az `inventory_ai_clean` adatai és sémája nem változtak; az 1000 sor előtte/utána hash-e egyezik. Írás kizárólag a külön ideiglenes tesztklaszterek fixture-jeiben történt. Qdrant-művelet nem történt.

**Kézi ellenőrzés:** indítsd újra a Streamlitet, töltsd fel újra a dokumentumot, és futtasd újra az **Analyze document → Egyeztetés az adatbázissal** lépéseket. A régi sessionben megőrzött eredmény nem friss mérés. Ellenőrizd a csoportokat, az egyedi eltérésszámot és a CSV-t. Élő LLM-kinyerés és az eredeti T15 szkennelt dokumentum felismerési minősége külön kézi/élő próbát igényel; ezeket ebben a munkában nem mértük meg.
