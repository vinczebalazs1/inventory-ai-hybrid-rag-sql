# Tiszta InventoryAI tesztadatbázis

## Cél és állapot

Az `inventory_ai_clean` önálló PostgreSQL-adatbázis: egy sor egy fizikai eszköz.
A meglévő `inventory` adatbázisból sem adatot, sem hibás azonosítót nem vesz át.
**A felhasználó helyi adatbázisát ez a fejlesztés nem hozta létre és nem töltötte fel.**
A létrehozás, migráció és betöltés valódi, elkülönített ideiglenes PostgreSQL-en
tesztelt. A helyi telepítést az alábbi lépések teszik külön, kifejezetten indíthatóvá.

A 2026-10-17-i, nyolc duplikált leltári számot találó
[régi audit](inventory_number_migration.md) az `inventory` akkori állapotáról szól.
Nem az új adatkészlet auditja, nem írjuk át és nem javítjuk automatikusan az adatait.

## Séma és üzleti döntések

`public.inventory_items`, pontosan a meglévő `config/schema.json` 11 oszlopa:

| Mező | PostgreSQL-típus | Clean feltétel |
|---|---|---|
| item_code | text | NOT NULL, legalább egy nem whitespace karakter; ismétlődhet |
| sub_code | integer | NOT NULL; a generált készletben 0 |
| activation_date | date | NOT NULL; a generátor rögzített történeti intervallumot használ |
| name | text | NOT NULL, legalább egy nem whitespace karakter |
| purchase_value | integer | NOT NULL, >= 0 |
| depreciation | integer | NOT NULL, >= 0 |
| current_value | integer | NOT NULL, >= 0 |
| currency | text | NOT NULL, három nagybetűs kód; a generált készlet HUF |
| quantity | integer | NOT NULL, CHECK (quantity = 1) |
| inventory_number | text | NOT NULL, UNIQUE, `^L-[0-9]{5,}$` |
| location | text | NOT NULL, legalább egy nem whitespace karakter |

A `clean_inventory_unique` UNIQUE megszorításhoz PostgreSQL egyedi B-tree indexet
hoz létre. A cikkszámon és a `(item_code, sub_code)` páron nincs UNIQUE. Nincs új
`id`, UUID, serial oszlop vagy módosított pénzügyi adattípus.

A `L-00001` azonosító szöveg marad; a vezető nullák megmaradnak. A formátum a
szintetikus környezet szabálya, nem a régi adatbázisra ráerőltetett korlátozás.
Minden mező kitöltött a clean készletben, ezért itt mind a 11 NOT NULL.
Az adatbázis nem tartalmaz idővel változó `CURRENT_DATE` CHECK-et.

A projekt a depreciation mezőt eddig csak „Depreciation amount” néven írta le;
nem volt általános számviteli invariáns. Ezért a `current_value = purchase_value -
depreciation` összefüggést a **szintetikus generátor és verifier** ellenőrzi,
nem vezettük be minden jövőbeli adatra érvényes adatbázis-szabályként.

A CHECK NULL értéknél önmagában nem elég, ezért külön NOT NULL is van.
Lásd a [PostgreSQL megszorítások dokumentációját](https://www.postgresql.org/docs/18/ddl-constraints.html).

## Biztonságos működés

- A CLI-k a kijelölt helyi env-fájlból és a shellből olvasnak. Eltérő `DB_*`
  értékeknél leállnak, és csak a változó nevét írják ki, a jelszót nem.
- `DB_NAME` csak `inventory_ai_clean` lehet. A kapcsolat tényleges adatbázisát
  `SELECT current_database()` ellenőrzi, az import minden batch előtt ismételten.
- Alapértelmezés: dry-run. Íráshoz **mindkettő** kell:
  `--apply --confirm-db inventory_ai_clean`. Nincs általános `--force`.
- A create művelet a `postgres` karbantartási adatbázisra kapcsolódik, ezt külön
  ellenőrzi. Csak a rögzített clean adatbázis nevét hozhatja létre.
- A séma és a megszorítások definícióját ellenőrizzük; a név önmagában nem elég.
  Ismeretlen kezelt tábla, extra oszlop, RLS, öröklődés, felhasználói trigger vagy
  rewrite rule esetén nincs import. A meglévő idegen táblát nem vesszük át.
- Az importer tranzakciós táblazár után ellenőrzi az ürességet. Azonos teljes
  tartalomnál `already_loaded`, eltérő nem üres tartalomnál hiba; nincs összeolvasztás.
- Paraméterezett `execute_values` batch insert, majd ugyanazon tranzakcióban
  teljes tartalom-hash ellenőrzés. Hiba vagy megszakítás: rollback.
- 5 másodperc kapcsolódási/zárvárakozási és 60 másodperc utasítási időkorlát.
- A verifier csak olvasó REPEATABLE READ tranzakcióban dolgozik; lekérdezései SELECT-ek.
- A betöltés nem hív LLM-et, nem indít Qdrant-indexelést, és nem írja át a `.env`-et.

Az adatbázis létrehozása külön autocommit lépés, mert a
[CREATE DATABASE nem futtatható tranzakcióblokkban](https://www.postgresql.org/docs/18/sql-createdatabase.html).
A tömeges betöltés a [psycopg2 execute_values](https://www.psycopg.org/docs/extras.html#psycopg2.extras.execute_values)
segédfüggvényt használja; az adatok kötött paraméterek, nem összefűzött SQL-részletek.

## Windows + pgAdmin 4: tíz lépés

Az alábbi író műveleteket akkor indítsd el, ha kifejezetten jóváhagytad az
`inventory_ai_clean` cél létrehozását és feltöltését. A régi `inventory`-t hagyd meg.
PowerShellben a repository gyökérkönyvtárából dolgozz.

### 1. Új adatbázis létrehozása

pgAdminban a helyi szerveren: **Databases → Create → Database**.
Név: `inventory_ai_clean`. Tulajdonos: az általad kijelölt adminisztratív/seedelő
felhasználó. Meglévő ilyen nevű adatbázist ne törölj és ne üríts ki.

SQL-változat a `postgres` Query Tool ablakában, autocommit mellett, külön futtatva:

```sql
CREATE DATABASE inventory_ai_clean TEMPLATE template0 ENCODING 'UTF8';
```

CLI-alternatíva az alább elkészített admin env-fájllal:

```powershell
venv\Scripts\python -m scripts.prepare_inventory_database create --env-file .env.clean.local
venv\Scripts\python -m scripts.prepare_inventory_database create --env-file .env.clean.local --apply --confirm-db inventory_ai_clean
```

Az első parancs megmutatja a tervet. A második létrehoz, vagy `already_exists`
állapotot ad; a már létező adatbázis tartalmát nem módosítja.

### 2. Tábla és megszorítások

Nyisd meg **az új adatbázis** Query Tool ablakát. Először:

```sql
SELECT current_database();
```

Az eredmény legyen `inventory_ai_clean`. Nyisd meg és futtasd egymás után:

1. [001_create_inventory_items.sql](../migrations/clean/001_create_inventory_items.sql)
2. [002_add_inventory_constraints.sql](../migrations/clean/002_add_inventory_constraints.sql)

Mindkettőben céladatbázis-ellenőrzés van. Ne futtasd a régi üzleti
`migrations/001_inventory_number_unique.sql` migrációt ezen folyamat részeként.

Készíts helyi admin konfigurációt:

```powershell
Copy-Item .env.clean.example .env.clean.local
```

A `.env.clean.local` `DB_USER` és `DB_PASSWORD` mezőibe a clean adatbázis létrehozó/
seedelő hozzáférését írd, `DB_NAME=inventory_ai_clean` mellett. Ez a fájl gitignore alatt van.
Az app olvasófelhasználója külön lesz beállítva a 6. lépésben.

Parancssoros alternatíva a táblákhoz, az új adatbázis létrejötte után:

```powershell
venv\Scripts\python -m scripts.prepare_inventory_database migrate --env-file .env.clean.local
venv\Scripts\python -m scripts.prepare_inventory_database migrate --env-file .env.clean.local --apply --confirm-db inventory_ai_clean
```

A dry-run sémavizsgálat, nem tranzakcióban visszagörgetett próbaírás. Hiányzó
táblánál ezt jelzi. A tényleges futtatás együtt, atomikusan alkalmazza a két SQL-t.

### 3. Pontosan 1000 tesztrekord és dokumentumok

```powershell
venv\Scripts\python -m pip install -r requirements-dev.txt
venv\Scripts\python -m scripts.generate_inventory_data --seed 42 --count 1000 --output data/synthetic --documents
```

Maga a generálás hálózat nélkül fut; a függőségek telepítése külön lépés.
A repository már tartalmazza az eredményt. A parancs újra előállítja ugyanazt a
CSV/JSON-t és a dokumentumokat; a manifest keletkezési időpontja változhat.

### 4. Ellenőrzött import

```powershell
venv\Scripts\python -m scripts.load_inventory_data --env-file .env.clean.local --dataset data/synthetic
venv\Scripts\python -m scripts.load_inventory_data --env-file .env.clean.local --dataset data/synthetic --apply --confirm-db inventory_ai_clean --report evaluation/clean_inventory/local_load.json
```

Az első parancs nem ír. A második csak a megerősített, ellenőrzött, üres táblába
importál. Újrafuttatáskor a teljes tartalomnak kell egyeznie. Más adatok esetén
megáll: nincs automatikus törlés, átnevezés, átszámozás vagy upsert.

### 5. Automatizált ellenőrzés

```powershell
venv\Scripts\python -m scripts.verify_inventory_data --env-file .env.clean.local --dataset data/synthetic --report evaluation/clean_inventory/local_verification.json
```

Elvárt: `validation_passed: true`, 1000 sor, 1000 különböző leltári szám,
`constraints_verified: true`, `dataset_hash_verified: true`. A hibakód 0 siker,
1 eltérés/hiba. Hiba nem jelenti azt, hogy az adatbázis üres vagy rendben van.

### 6. Olvasófelhasználó és az app `.env` beállítása

pgAdmin **Login/Group Roles → Create → Login/Group Role**:
`inventory_ai_reader`, saját helyi jelszó, login engedélyezve. Ne legyen superuser,
CREATEDB, CREATEROLE, táblatulajdonos vagy író csoport tagja.
Az új adatbázis Query Tool ablakában, tulajdonosként:

```sql
DO $reader$
BEGIN
    IF current_database() <> 'inventory_ai_clean' THEN
        RAISE EXCEPTION 'Wrong target database';
    END IF;
    GRANT CONNECT ON DATABASE inventory_ai_clean TO inventory_ai_reader;
    GRANT USAGE ON SCHEMA public TO inventory_ai_reader;
    GRANT SELECT ON public.inventory_items TO inventory_ai_reader;
END
$reader$;
```

Az alkalmazás meglévő `.env` fájlját **kézzel** állítsd át; a többi API-/Qdrant-
beállítást tartsd meg:

```dotenv
DB_NAME=inventory_ai_clean
DB_HOST=localhost
DB_PORT=5432
DB_USER=inventory_ai_reader
DB_PASSWORD=your_own_local_password
```

A shellből örökölt változókat a `load_dotenv()` nem írja felül. Új PowerShell
ablakban dolgozz, vagy a már nem kívánt DB-változókat távolítsd el a folyamatból.
Változóneveket titkok kiírása nélkül így nézhetsz meg:

```powershell
Get-ChildItem Env:DB_* | Select-Object Name
```

Az admin CLI a két forrás közötti eltérést megtagadja. Az alkalmazás meglévő
kapcsolatkezelése változatlan, ezért a kézi konfigurációváltás után teljes újraindítás kell.

### 7. InventoryAI indítása

```powershell
venv\Scripts\python -m streamlit run app/web/simple_server.py
```

### 8. Konkrét eszköz keresése

Az alkalmazásban: „Hol található az L-00001 leltári számú eszköz?”
Ez az ág LLM-hozzáférést is igényel. Az adatbázis önálló ellenőrzése pgAdminban:

```sql
SELECT inventory_number, item_code, name, quantity, location
FROM public.inventory_items WHERE inventory_number = 'L-00001';
```

A seed 42 készletben: `L-00001`, `LAT5540`, `Dell Latitude 5540`, 1, `LIB`.

### 9. Kontrollált dokumentum

**Dokumentum elemzése – PDF / DOCX** panel → töltsd fel
[D01.docx](../data/synthetic/documents/D01.docx) vagy
[D01.pdf](../data/synthetic/documents/D01.pdf) → **Analyze document** →
**Egyeztetés az adatbázissal**. Ezután próbáld a D02 helyszínváltozás-mintát.

### 10. Eredmény ellenőrzése

- D01: megfelelő kinyerés mellett EXACT_MATCH, ATTACH_DOCUMENT, nincs frissítés.
- D02: ugyanaz a rekord, `LIB → NIK`, UPDATE_CANDIDATE és emberi ellenőrzés.
- A javaslatok nem hajtanak végre adatbázis-módosítást vagy dokumentumcsatolást.
- A Qdrant tartalmát nem szinkronizáltuk az új leltárral; a HYBRID dokumentumai
  továbbra is a korábbi külön dokumentumtárból származnak.

Az API nélküli, valódi adatbázisos 16 esetes mérés:

```powershell
venv\Scripts\python -m scripts.evaluate_clean_inventory --postgres --env-file .env.clean.local --dataset data/synthetic --report evaluation/clean_inventory/local_matching.json
```

Ez ismert strukturált mezőket használ, nem élő LLM-kinyerést. A két ismert
státuszeltérés miatt 1-es visszatérési kód is a mérés érvényes eredménye; részletek:
[tesztelés és korlátok](clean_inventory_testing.md).
