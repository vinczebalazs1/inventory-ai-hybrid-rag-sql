# InventoryAI – PostgreSQL-konfiguráció és funkcionális ellenőrzés

**Dátum:** 2026-11-08, Europe/Budapest. **Branch / HEAD:** `main` / `a7bd4278aaa4a7da6aa7375ff1741c6e9107ab83`.

**Összesített döntés: a clean adatbázisra váltás IGAZOLT; a teljes élő rendszer működése NEM IGAZOLT.** A konfigurált alkalmazáskapcsolat, a régi SQL-végrehajtó és az új rekordegyeztetés ténylegesen eléri az `inventory_ai_clean` adatbázist. Az élő Qdrant-próba kapcsolati hibával sikertelen; élő LLM-hívás nem történt. Ezért nem állítom, hogy minden elfogadási feltétel maradéktalanul teljesült.

## 1. Előtte és utána: melyik adatbázist használja az alkalmazás?

| Ellenőrzött tulajdonság | Előtte | Utána |
|---|---|---|
| `.env` céladatbázisa | `inventory` | **`inventory_ai_clean`** |
| Alkalmazáskapcsolat | Hitelesítési hiba | Sikeres; `current_database()` = `inventory_ai_clean` |
| Felhasználó | `postgres` | `postgres`, meglévő helyi hitelesítéssel |
| Tranzakció alapállapota | Nem volt külön alkalmazásoldali read-only alapbeállítás | `default_transaction_read_only=on`; az ellenőrzött tranzakciók is read-only |
| Régi SQL-ág | Hibás konfiguráció akadályozta | Élő lekérdezés: **1000 rekord** |
| Új egyeztető | Ugyanazt a kapcsolódást használta | Élő clean keresés és Streamlit-egyeztetés sikeres |

A közös [get_connection](../app/db/connection.py#L12) `DB_*` környezeti változókból kapcsolódik. Importkor a `load_dotenv()` betölti a `.env` fájlt, de a már létező folyamatkörnyezeti értékeket nem írja felül. A régi [execute_query](../app/db/executor.py#L19) és az új [InventoryRepository._transaction](../app/record_matching/repository.py#L107) ugyanazt a függvényt használja; ezt objektumazonossággal és tényleges lekérdezésekkel is ellenőriztem. A `.env.clean.local` az adminisztrációs eszközök külön konfigurációja, nem automatikus Streamlit-beállítás.

Az ellenőrzéskor nem találtam futó Streamlit-folyamatot, és az ellenőrző folyamat nem örökölt felülíró `DB_*` értékeket. A tényleges webes belépési pontot AppTesttel is futtattam, élő clean egyeztetéssel. Új terminálból az indítás:

```powershell
venv\Scripts\python -m streamlit run app/web/simple_server.py
```

Más környezetből indítva az örökölt változókat külön ellenőrizni kell. A régi `scripts.run_webapp` segéd elavult `run_server` importot tartalmaz; a fenti, README szerinti indítást kell használni.

## 2. Pontos változtatások és kompatibilitás

**Módosított meglévő fájlok:**

- `.env`: `DB_NAME` → `inventory_ai_clean`; a hibás `DB_PASSWORD` helyett a már működő `.env.clean.local` megfelelő értéke; új `PGOPTIONS='-c default_transaction_read_only=on'`.
- [.env.example](../.env.example): clean alapértelmezett adatbázisnév és ugyanez a read-only kapcsolati opció, titkos adat átmásolása nélkül.

Mindkettőről bájtpontos, változtatás előtti mentés készült: `.cache/configuration_backups/2026-11-08_1095eed7/.env` és `.env.example`. Ez a könyvtár Git által figyelmen kívül hagyott; a mentett `.env` titkos adatokat tartalmaz, ezért nem szabad publikálni. A `.env.clean.local`, az API-/Qdrant-beállítások, az alkalmazáskód, a meglévő tesztek és a korábbi riportok változatlanok.

**Jogosultsági korlát:** `inventory_ai_reader` szerepkör nincs a helyi szerveren, és külön reader-hitelesítés sem áll rendelkezésre. Nem hoztam létre új felhasználót vagy superusert. A meglévő `postgres` használata megmaradt; a `PGOPTIONS` read-only alapállapotot ad, **nem jogosultsági szintű írásvédelmet**. A korlátozott alkalmazásfelhasználó későbbi beállítása továbbra is ajánlott. Az új egyeztető saját read-only tranzakcióvédelme változatlan.

**A két adatbázis séma szerint kompatibilis, adataiban eltér.** Mindkettő ugyanazt a 11 oszlopot és típust tartalmazza; a [schema.json](../config/schema.json), a szöveg–SQL prompt és a mezőmegfeleltetés használható a clean táblával is. A clean készletben a leltári szám egyedi és kötelező, a cikkszám ismétlődik; a [sémaleírás](../config/schema_descriptions.yaml) ezt helyesen kezeli. Az egyeztető az egyediséget a tényleges adatbázisban ellenőrzi, nem a névből feltételezi.

A régi adatbázis 20 különböző eszköznevével/6 helyszínével szemben a clean 26 modellnevet/5 helyszínt tartalmaz. Régi konkrét cikkszámok vagy UI-példák ezért adhatnak üres találatot. Demonstrációhoz például az `L-00001` leltári szám használható. A Qdrant névalapú HYBRID-szűrésének találati lefedettsége az új modellnevekre külön kérdés; sémaegyezésből nem következik dokumentációs egyezés.

## 3. Tényleges ellenőrzések és elfogadási állapot

| Ellenőrzés | Eredmény és bizonyítási határ |
|---|---|
| Alkalmazáskapcsolat és régi SQL-végrehajtó | **IGAZOLT, élő PG:** clean cél, 1000 sor, read-only állapot. |
| Új exact/fuzzy keresés, eltérések, javaslatok | **IGAZOLT, élő PG, ismert mezőbemenet:** 16 eset döntései egyeznek a régi PG-riporttal; a referencia **14/16**. D05/D06 továbbra is `SEARCH_INCOMPLETE`, eltérő referencia-kategória mellett. |
| PDF/DOCX → processing → PG | **IGAZOLT helyettesített LLM-mel:** D01 és D02 mindkét formátuma, valódi Docling és clean DB. D01: `EXACT_MATCH`/csatolási javaslat. D02: helyszíneltérés, frissítési és kéziellenőrzési javaslat. |
| Streamlit-megjelenítés | **IGAZOLT AppTesttel:** valódi belépési pont és egyeztető gomb, élő clean DB, 0 UI-kivétel; eltérés és frissítési javaslat megjelent. AI helyettesített, Qdrant memóriabeli. |
| SQL/RAG/HYBRID adatfolyam | **IGAZOLT ellenőrzött helyettesítésekkel:** mindhárom útvonal sikeres; SQL/HYBRID tényleges clean adatot olvasott. LLM/embedding helyettesített, Qdrant memóriabeli. |
| Régi PDF/TXT tudástárfeltöltés | **IGAZOLT tesztben:** mindkét formátum feldolgozása, pontképzés, szemantikus és névszűrt visszakeresés. Csak memóriabeli tárolás történt. A tesztadapter a telepített REST-kliens `PointsList` validációját alkalmazta. |
| Élő Qdrant / teljes élő RAG és HYBRID | **SIKERTELEN kapcsolati próba / NEM IGAZOLT teljes működés.** DNS-feloldás sikerült, de a kollekciómetaadat olvasása `ConnectionResetError`, Windows **10054** hibába futott. Azonos hoszton a 443-as kontrollpróba is sikertelen. Nem bizonyított API-kulcshiba; a szolgáltatói hozzáférés eredménye sem állapítható meg. |
| Élő LLM-es SQL-generálás, válaszadás, extraction/mapping | **NEM IGAZOLT:** a kérés szerint nem indult élő LLM-/embedding-API-hívás. |
| Adatvesztés, korábbi riportok változása | **Változatlanság IGAZOLT:** mindkét leltártábla előtte/utána 1000 sor, azonos teljes tartalmi hash, oszlopok és megszorítások; a régi mérési fájlok hash-e változatlan. Éles Qdrant-írás nem indult. |

**Meglévő tesztek:** **230 PASS, 81 SKIP, 0 FAIL, 0 ERROR**, 33,800 másodperc. Mind a 81 kihagyás a nem engedélyezett, ideiglenes PG-klasztert létrehozó integrációs tesztcsoporthoz tartozik. A helyi Docling PDF-teszt futott; a tesztfuttató tiltott minden külső HTTP- és valódi DB-kapcsolatot. Az élő read-only PG-próbák külön futottak. Ez **nem új 311 PASS** eredmény.

Bizonyítékok: [sikeres JUnit](../evaluation/configuration_check_2026-11-08_1095eed7/tests_attempt_02/test_results.xml), [funkcionális eredmények](../evaluation/configuration_check_2026-11-08_1095eed7/functional_attempt_02/functional_checks.json), [verzió-, hash- és DB-ellenőrzés](../evaluation/configuration_check_2026-11-08_1095eed7/run_metadata.json). A kezdeti segédfuttatói hibák naplói is megmaradtak; a javítások kizárólag az új ellenőrző segédprogramokat érintették.

## 4. PostgreSQL és Qdrant a végleges architektúrában

A **PostgreSQL** a strukturált leltári tényeket adja mindkét alkalmazáságnak. A **Qdrant** a régi RAG tudástár szövegrészleteit és vektorait tárolja. Nincs köztük tartós rekord-/dokumentumkapcsolat; a HYBRID névszűrést és szükség esetén szemantikus visszakeresést használ. Az új PDF/DOCX-modul nem indexel Qdrantba, és nem ment PostgreSQL-be: ellenőrizhető, nem végrehajtható javaslatokat jelenít meg a sessionben. Forrás: [answer_hybrid_details](../app/rag/retrieval/rag_service.py#L105), [reconcile_document](../app/record_matching/reconciliation_service.py#L25).

## 5. Kell-e még az eredeti `inventory`?

**A jelenlegi alkalmazásfunkciókhoz nem kötelező.** Nincs olyan aktív futásidejű kód, amely kifejezetten ezt az adatbázisnevet követelné; a clean mindkét PostgreSQL-ágat kiszolgálja. A korábbi `inventory` hivatkozások történeti dokumentációban, visszaállítási mentésben és védelmi tesztekben maradnak. Az integrációs tesztek az azonos nevű védelmi adatbázist saját ideiglenes klaszterükben készítik el, nem a fejlesztő régi adatbázisát igénylik.

**Most változatlanul megmaradt.** Eltávolítása elveszítené az eredeti adatokkal, köztük a 8 duplikált leltáriszám-csoporttal végzett visszaellenőrzés lehetőségét. Későbbi megszüntetés előtt védett `pg_dump` mentés, szükséges szerepkör-/jogosultságmentés, külön környezetben sikeres visszaállítás, darabszám-/hash-/constraint-ellenőrzés, valamint külső programok és feladatok függőségvizsgálata kell. A repository auditja nem igazolja, hogy más helyi alkalmazás sem használja.

## 6. Hátralévő teendők és fájlok

1. **Élő Qdrant-elérés rendezése:** a meglévő cluster/végpont és hálózati elérés ellenőrzése; sikeres read-only próba után a clean eszköznevek dokumentációs lefedettségének vizsgálata. URL-t vagy hitelesítést nem találtam ki, TLS-védelmet nem lazítottam.
2. **Reader szerepkör és valós LLM-bizonyíték:** külön felhasználó megfelelő hitelesítésével kiváltani a megmaradt adminisztrátori kapcsolódást; a bemutatóhoz később korlátozott, dokumentált élő LLM-próbát végezni. Ezek most nem igazolt részek.

Az összes módosított meglévő fájl: **`.env`, `.env.example`**. Új jelentés: **`docs/thesis_database_configuration_check.md`**. Új bizonyítékkönyvtár: `evaluation/configuration_check_2026-11-08_1095eed7/`, benne `run_tests.py`, `verify_functional.py`, `run_metadata.json`, a kezdeti és sikeres próbák JSON/XML/napló fájljai, `file_changes.json` és `artifact_hashes.json`. A [teljes fájljegyzék](../evaluation/configuration_check_2026-11-08_1095eed7/file_changes.json) a mentéseket és az elkülönített `.cache` tesztállományokat is felsorolja. Forráskód, meglévő teszt és korábbi mérési riport nem módosult.

**Közérthetően:** SQL-kérdésnél az AI lekérdezést javasol, az ellenőrzött SQL a clean leltárból olvas, majd az AI választ fogalmaz. RAG-kérdésnél dokumentumrészleteket keres a Qdrantban, és ezekből válaszol; ennek élő kapcsolata most hibás. Új PDF/DOCX esetén a Docling olvasható tartalmat készít, az LLM mezőket nyer ki és rendel a sémához, majd külön gombbal determinisztikus összevetés történik a clean leltárral. Az eltérésekből javaslat készül, automatikus adatátírás nélkül.
