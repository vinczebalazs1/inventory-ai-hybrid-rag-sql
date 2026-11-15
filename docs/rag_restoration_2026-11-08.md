# InventoryAI – Qdrant/RAG helyreállítás, 2026-11-08

**Eredmény:** a `devices` tudástár helyreállt. A kollekcióban **40 pont**, kizárólag az `app/rag/data/devices.txt` **10 eszközleírásából** származó chunk található. Az SQL, RAG és HYBRID egy-egy tényleges, élő próbája sikerült. A PostgreSQL adatai és a korábbi mérési riportok változatlanok.

Git HEAD: `a7bd4278aaa4a7da6aa7375ff1741c6e9107ab83`. Ez a futás munkakönyvtári állapot: a kliensfüggőség az alábbiak szerint módosult, még nincs commitolva.

Bizonyítékok: [`evaluation/rag_restore_2026-11-08_90ed2390/`](../evaluation/rag_restore_2026-11-08_90ed2390/).

## Kompatibilitás és célcluster

A kezdeti állapotban a Python kliens **1.17.1**, a szerver **1.20.0** volt. A telepített kliens saját `is_compatible` ellenőrzése erre `false` értéket adott. A három minor verziónyi eltérés kívül esett a támogatott kompatibilitási tartományon; ez indokolta a frissítést. A Qdrant hivatalos [kompatibilitási tájékoztatója](https://qdrant.tech/documentation/faq/qdrant-fundamentals/) és a [qdrant-client 1.20.0 csomagoldala](https://pypi.org/project/qdrant-client/1.20.0/) szolgált külső ellenőrzésül.

A `requirements.txt` pin és a virtuális környezet **1.20.0-ra** frissült. A telepítési terv és az előtte/utána csomaglista alapján **csak a qdrant-client változott**, más függőség nem. A `pip check` sikeres. A végső kliens/szerver pár **1.20.0 / 1.20.0**, kompatibilis; a kapcsolat kompatibilitás-ellenőrzése bekapcsolva maradt.

A tényleges cél a `.env` `QDRANT_URL` és `QDRANT_API_KEY` beállításaiból töltődött. A feltöltés előtt a cluster kollekciólistája üres volt; nem volt megőrzendő pont vagy más kollekció. Az endpoint azonosságát hash rögzíti, kulcsot és jelszót nem mentettünk a riportba.

## Egyszeri feltöltés és visszaolvasás

A meglévő `app.rag.ingestion.ingestion_service.ingest_devices` folyamat **egyszer** futott, a tényleges `devices.txt` bemenettel. A mérőburkolat előzetesen ellenőrizte a célt és a forrást, számlálta az API-hívásokat, majd visszaolvasta a feltöltött pontokat. Nem helyettesítette a szolgáltatások válaszait. Az automatikus embedding-újrapróbálkozás ennél a futásnál ki volt kapcsolva; a betöltést nem ismételtük.

| Ellenőrzés | Tényleges eredmény |
|---|---|
| Forrás | `app/rag/data/devices.txt` |
| Forrás SHA-256 | `dedffbfdabc6fb7f227681f5913248919ec45274c626bfe60da24f8cd248a3a0` |
| Eszköz / chunk / visszaolvasott pont | **10 / 40 / 40** |
| Embeddingmodell | `text-embedding-3-large` |
| Vektorméret / távolság | **3072 / Cosine** |
| Payloadmezők | `name`, `section`, `text`, `source`, `doc_type` |
| Forrásjelölők | `source=devices.txt`, `doc_type=device_txt` |
| Payloadindex | **`name`: keyword** |
| Kollekció végállapota | **green** |
| Pontazonosítók és payloadok | Mind a 40 pontosan megfelel a forrásból előállított elvárt értéknek |
| Feltöltési embeddinghívások | **40 sikeres / 40 próbálkozás, 950 token** |

Indexelt nevek: `desk`, `docking station`, `laptop`, `microphone`, `monitor`, `nas`, `printer`, `server`, `smartphone`, `switch`. Mindegyikhez négy rész tartozik: description, usage, troubleshooting, notes. A szintetikus D01–D16 dokumentumokat nem indexeltük.

Részletes bizonyíték: [ingestion.json](../evaluation/rag_restore_2026-11-08_90ed2390/ingestion.json). Az `ingest_once.py` ugyanannak a futásnak az újraindítását jelzőfájllal tiltja; **nem szükséges ismét feltölteni**.

## Funkcionális próbák

A függőségfrissítés után az érintett dokumentumfeldolgozási regressziós, ingestion- és SQL-validator tesztek: **10 passed**, 1,49 s. Parancs:

```powershell
venv\Scripts\python -B -m pytest -q -p no:cacheprovider tests/test_document_regression.py tests/test_document_ingestion.py tests/test_sql_validator.py --junitxml=evaluation/rag_restore_2026-11-08_90ed2390/preflight_tests.xml
```

Ezután a valódi szolgáltatásokkal, az alkalmazás tényleges `handle_question` belépési pontján három kérdést futtattunk. A kiválasztott útvonal mindháromnál megfelelt az elvártnak.

| Próba | Ellenőrzött eredmény |
|---|---|
| Külön szemantikus keresés: nem válaszoló nyomtató | Első találat: `printer`, `troubleshooting`, `devices.txt`; score: **0.6484557**. |
| SQL: hány leltári rekord van? | `COUNT(*)` eredménye **1000** az `inventory_ai_clean` adatbázisban; a válasz ezt közölte. |
| RAG: nem válaszoló nyomtató hibaelhárítása | A válasz a tápellátás, kábelek és hálózat ellenőrzését javasolta, a nyomtató megfelelő chunkja alapján. |
| HYBRID: L-00001 helye, neve és a nem induló laptop hibaelhárítása | SQL: **LIB, Dell Latitude 5540**. Dokumentum: `laptop` troubleshooting. A válasz a helyet/nevet és az akkumulátor/töltő ellenőrzését adta vissza. |

A funkcionális próbák **8 sikeres chat/LLM-kérést (2247 token)** és **4 sikeres embeddingkérést (83 token)** igényeltek. A routing, SQL-generálás és válaszgenerálás külön hívások, ezért három kérdéshez nyolc LLM-kérés tartozott. A teljes helyreállítás összesen **44 embeddingkérés (1033 token)** és **8 chatkérés** volt. API-hiba vagy automatikus újrapróbálkozás nem történt.

Bizonyíték: [live_checks.json](../evaluation/rag_restore_2026-11-08_90ed2390/live_checks.json), benne a kérdések, generált SQL-ek, eredmények, válaszok és visszakeresési nyomvonalak. Ez néhány funkcionális próba, **nem teljes pontosságmérés, teljes tesztsuite vagy böngészős felületteszt**. A mentett similarity score nem kalibrált valószínűség.

## A HYBRID néveltérése és korlátja

A clean adatbázis **26 különböző teljes modellneve** és a tudástár **10 általános eszközneve** között kisbetűsítés és trim után **nincs pontos egyezés**.

A tényleges HYBRID-próba nyomvonala:

```text
L-00001 → SQL: Dell Latitude 5540, LIB
name = "dell latitude 5540" → Qdrant: 0 találat
szemantikus tartalékkeresés → laptop / docking station / laptop
válasz → SQL-adatok + általános laptopos hibaelhárítás
```

A HYBRID tehát működött a szemantikus tartalékkereséssel. A név szerinti szűrés a jelenlegi clean modellnevekre nem hoz egyezést. Az általános `laptop` leírás **nem Dell Latitude 5540-specifikus kézikönyv**, és a payloadban továbbra sincs közös leltári/SQL-rekordazonosító. Modellhez garantáltan kapcsolódó dokumentációhoz később külön megfeleltetés vagy modellazonosítóval ellátott eredeti dokumentum szükséges. Ilyen adatot most nem találtunk ki és nem indexeltünk.

## Változatlanság, módosított fájlok

A PostgreSQL-ellenőrzés és az alkalmazás SQL-próbái read-only kapcsolattal futottak. Az `inventory_items` 1000 teljes sorának rendezett JSON-reprezentációjából képzett hash előtte/utána azonos:

```text
35b4d94c418fe16ee1a899c0b22a39fc6d0f8e30e38c940400795ac79768486e
```

A kiinduláskor rögzített **208 fájlból 207 változatlan**. Az egyetlen módosított korábbi fájl a **`requirements.txt`**: `qdrant-client==1.17.1` → `qdrant-client==1.20.0`, eredeti sorvégformátummal. A `.env`, alkalmazáskód, tesztforrások, `devices.txt` és régi riportok nem változtak. A már korábban módosított `.env.example`-hez nem nyúltunk.

Új fájl ez a dokumentum, valamint az elkülönített `evaluation/rag_restore_2026-11-08_90ed2390/` futási könyvtár: előzetes állapot, telepítési terv/riport, két futtatási segéd, feltöltési és élő teszteredmények, JUnit, végellenőrzés és artefaktumhash-ek. API-kulcsot vagy jelszót nem tartalmazhatnak.

**Hatás a korábbi forrásaudit állítására:** a clean riportok 84 fájlos manifestjéből most **83/84 egyezik**; kizárólag a szándékosan frissített `requirements.txt` tér el. A korábbi `matching_metrics.json` eredeti 63 fájlos forrásköre továbbra is **63/63 egyezik**. A régi matchingeredményeket nem mértük újra és nem írtuk át; a korábbi 84/84 állítást annak auditdátumával kell kezelni. A jelenlegi RAG-helyreállítást ezek az új bizonyítékok dokumentálják.

Végellenőrzés: [final_verification.json](../evaluation/rag_restore_2026-11-08_90ed2390/final_verification.json). A szolgáltatásokat érintő további helyreállítási hiba nem maradt; a HYBRID modellnév-megfeleltetés fenti korlátja fennáll.
