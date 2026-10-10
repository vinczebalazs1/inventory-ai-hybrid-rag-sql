# Dokumentumfeldolgozás V1

## Cél és adatfolyam

PDF/DOCX → Docling → általános mezőkinyerés → séma szerinti szemantikus
megfeleltetés → normalizálás és validáció → Streamlit előnézet.

A külön elemzési ág nem hív PostgreSQL-t vagy Qdrantot, nem ment rekordokat,
és nem végez rekordegyeztetést. A meglévő PDF/TXT RAG-feltöltés, SQL/RAG/HYBRID
kérdezés a korábbi útvonalon működik tovább.

## Komponensek

Az `app/document_processing/` moduljai:

- `docling_parser.py`: bytes + filename → Docling `DocumentStream` →
  `DocumentConverter`. PDF és DOCX engedélyezett, 25 MB és 200 oldal korláttal.
  Nem használja a feltöltött fájlnevet helyi elérési útként, és nem hoz létre
  saját ideiglenes fájlt. A részleges konverzió hibának számít.
- `extraction_service.py`: bekezdéshatárokat kereső, karakterkorlátos darabolás;
  oldalanként továbbadott provenance; minden darab általános mezőlistája egyesül.
  Azonos label/value/evidence deduplikálódik az első igazolt oldalszám megtartásával;
  eltérő értékek megmaradnak.
- `llm_json.py`: a meglévő `app.services.llm_service.ask_llm` hívása, szigorú
  Pydantic JSON-validáció, legfeljebb egy javító hívás hibás válaszonként.
  A promptok az `app/prompts/document_*.txt` fájlokban találhatók.
- `field_mapper.py`: a schema service által betöltött aktuális oszlopnevek,
  típusok és leírások alapján batch LLM mapping. A válasz kizárólag index és
  célnév/null; az eredeti értéket és evidence-et a program másolja át.
  Hiányzó/duplikált index és nem létező célmező hibát okoz.
- `validation_service.py`: csak mapped mezőket normalizál. A séma integer
  típusait szigorúan kezeli (a jelenlegi pénzmezők is integer típusúak).
  Numerikus/decimal értékek normalizált decimális stringként maradnak pontosak.
  ISO és egyértelmű magyar dátumformák támogatottak. Kétértelmű ezres/tizedes
  elválasztó, tört integer, érvénytelen dátum vagy üres szöveg figyelmeztetés.
  Támogatott pénznemek: HUF/Ft/forint, EUR/€/euro, USD, GBP/£, CHF, JPY, CAD, AUD.
  A `$` önmagában kétértelmű. Hiba esetén raw_value megmarad, normalized_value null.
- `processing_service.py`: a teljes folyamatot összefogó `process_document(bytes,
  filename) -> ProcessingResult`. Szakaszonként felhasználóbarát hibát ad.
- `app/web/document_preview.py`: feltöltés, indítás, sessionben tartott eredmény,
  mapped/unmapped/validation táblák és raw expander.

## Adatmodellek és provenance

Pydantic 2 modellek: `ParsedDocument`, `ExtractedField`, `ExtractionResult`,
`MappedField`, `MappingResult`, `ValidationIssue`, `ProcessingResult`.
Az eredmény `model_dump(mode="json")` vagy `model_dump_json()` segítségével
szerializálható. Nincs dokumentumtípusonkénti séma vagy LLM confidence score.

A parser megőrzi a Docling markdown és dictionary reprezentációját. PDF esetén
a Docling valódi oldalkulcsaiból készülnek az oldalszövegek és `[PAGE n]` jelölők.
DOCX esetén nincs stabil lapozás: page=null. Az LLM által megadott evidence csak
akkor marad meg, ha whitespace-normalizálás után szerepel az adott chunkban.
Nem igazolható evidence és a hozzá kapcsolt oldalszám null lesz. Ez nem bizonyítja
az LLM értelmezésének helyességét, csak az idézet forrásbeli jelenlétét.

## Telepítés és használat

A fejlesztői környezet Python 3.11-et és Pydantic 2.12.5-öt használ.

```powershell
python -m venv venv
venv\Scripts\python -m pip install -r requirements-dev.txt
venv\Scripts\python -m scripts.prepare_docling_models
venv\Scripts\python -m streamlit run app/web/simple_server.py
```

A `.env` fájlban az `OPENAI_API_KEY` szükséges az extraction és mapping
hívásokhoz. Az elemzési ág nem igényel adatbázis-műveletet. A teljes meglévő
alkalmazás Qdrant kliensét továbbra is importálja a főfelület.

1. Nyisd ki a **Dokumentum elemzése – PDF / DOCX** panelt.
2. Tölts fel egy PDF vagy DOCX fájlt.
3. Kattints az **Analyze document** gombra.
4. Ellenőrizd a Document type, Mapped fields, Unmapped fields és Validation issues
   részeket, különösen az evidence és page oszlopokat.
5. A Debug / raw output panelen ellenőrizhető a szöveg, extraction és mapping JSON.
   A teljes Docling JSON csak Show debug mellett, legfeljebb 200 KB méretig látható.

Demo dokumentumszöveg:

```text
Asset Name: Dell Laptop
Inventory No.: INV-123
Location: Budapest
Service Tag: ABC123
Manufacturer: Dell
Warranty: 36 months
```

Az első három mező várhatóan mapped, az utolsó három unmapped.
A szemantikus döntést az LLM hozza; ezt az evidence alapján ellenőrizni kell.

## Konfiguráció

| Változó | Alapérték | Jelentés |
|---|---|---|
| DOCUMENT_CHUNK_SIZE | 12000 | Egy extraction chunk maximális karakterszáma |
| DOCUMENT_CHUNK_OVERLAP | 500 | Átfedés karakterben, kisebb a chunk méreténél |
| DOCUMENT_MAPPING_BATCH_SIZE | 80 | Egy mapping hívás mezőinek maximuma |
| DOCUMENT_LLM_MODEL | gpt-6-luna | A központi LLM wrappernek átadott modell |
| DOCUMENT_TARGET_TABLE | inventory_items | A schema.json kiválasztott táblája |
| DOCUMENT_ARTIFACTS_PATH | automatikus | Opcionális helyi Docling modellkönyvtár |

A debug viselkedést a meglévő Show debug kapcsoló vezérli.
A fájl-, oldal- és debug JSON-korlátok a `Settings` osztályban vannak központosítva.

## Függőségek és Docling API

Új runtime függőség: `docling==2.80.0`. A már használt, korábban a requirementsből
hiányzó `qdrant-client==1.17.1` szintén szerepel a listában. A fejlesztői
requirements tartalmazza a pytest-et. A requirements.txt UTF-8 kódolású lett.
Az OCR-függőség `rapidocr==3.3.1` verzióra rögzített: a későbbi 3.9-es kiadás
modellarchitektúra-nevei nem kompatibilisek a Docling 2.80 előre letöltött OCRv4
modelljeivel.

Docling API: [DocumentConverter](https://docling-project.github.io/docling/reference/document_converter/),
[DoclingDocument](https://docling-project.github.io/docling/reference/docling_document/).
Az első PDF-feldolgozás Docling modellek letöltését igényelheti; CPU-n lassú lehet.
A DOCX parser nem igényel PDF modelleket. A Docling a modellcache-be írhat;
a kinyert üzleti adatokat ez a modul nem persistálja.

A `python -m scripts.prepare_docling_models` parancs a szükséges PDF-modelleket
a gitből kizárt `.cache/docling/` könyvtárba tölti. A sikeres letöltést jelző
`.ready` fájl után a parser automatikusan ezt használja. Más könyvtár megadható
a DOCUMENT_ARTIFACTS_PATH változóval. Ez Windows alatt a Hugging Face párhuzamos
cache-inicializálásakor tapasztalt `WinError 1314` symlink jogosultsági hibát is
elkerüli: a letöltés normál helyi fájlokat használ. A letöltéshez internet kell.

## Tesztelés

```powershell
venv\Scripts\python -m pytest -q
venv\Scripts\python -m pytest tests/test_docling_pdf_smoke.py --run-docling-pdf -q
venv\Scripts\python -m pip check
```

A unit tesztek mockolják az LLM wrappert. A DOCX smoke teszt memóriában készített
valódi dokumentumot konvertál Doclinggal. A Streamlit AppTest a teljes UI indulását
ellenőrzi. A régi tesztfájlok egy része csak `main()` kézi demót tartalmaz; ezek nem
pytest tesztek, és egy részük élő szolgáltatást vagy Qdrant-írást végezne.

### Ellenőrzött eredmény (2026-09-27, Windows / Python 3.11.9)

- `venv\Scripts\python -m pytest -q --run-docling-pdf --tb=short`:
  **56 passed, 2 warnings**, 24,74 másodperc. Nincs kihagyott teszt ebben a futásban.
  A két DeprecationWarning a Docling belső PDF/OCR implementációjából ered.
- `venv\Scripts\python -m pip check`: **No broken requirements found**.
- `venv\Scripts\python -m compileall -q app scripts tests`: sikeres.
- `git diff --check`: sikeres; a Git csak LF/CRLF konverziós tájékoztatást adott.
- Valódi PDF/DOCX konverzió, teljes DOCX → mock LLM → mapping → validation
  folyamat, UI-indítás és három eredménytábla renderelése ellenőrizve.
- Az SQL/RAG/HYBRID ágak és a RAG-feltöltés külső hívásai mockoltak; a tesztgyűjtés
  memóriabeli Qdrant-klienst használ. Élő OpenAI-, PostgreSQL- vagy Qdrant-végponttal
  nem történt végpontok közötti teszt, és adatbázis-írás sem történt.

A kezdeti PDF smoke teszt előbb Windows symlink-jogosultsági hibát, majd
RapidOCR-modellnév inkompatibilitást jelzett. A helyi modell-előkészítő és a
rögzített RapidOCR-verzió után a PDF-teszt sikeres. Az alap `pytest -q` parancs
a PDF smoke tesztet szándékosan kihagyja; a fenti kapcsolóval futtatható.

## Korlátok és következő lépés

- Nincs kalibrált pontossági garancia; az LLM szemantikai tévedése lehetséges.
- A lapos mezőlista nem modellez teljes táblázati rekordkapcsolatokat.
- Darabolási határon átnyúló nagyon hosszú tény elveszhet; az átfedés mérsékli ezt.
- Karakterszám-alapú korlát van, nem tokenizer-alapú költségbecslés.
- Szinkron feldolgozás: nagy dokumentum hosszú ideig foglalhatja a UI munkamenetét.
- Egy hibás chunk vagy mapping batch megszakítja a teljes elemzést; nincs részleges
  eredményt sikeresként feltüntető fallback.
- A normál logok szakaszt, forrásnevet, darab-/mezőszámokat és hibakategóriát
  tartalmaznak. Dokumentumtartalom és provider exception-szöveg nem kerül beléjük;
  részletes hiba a debug felületen érhető el.

Következő iteráció: record matching → database comparison → delta detection →
human review. Ezek ebben a verzióban nem készültek el.
