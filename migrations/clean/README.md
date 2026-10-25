# Külön clean tesztadatbázis migrációi

Ezek a fájlok kizárólag az `inventory_ai_clean` környezethez tartoznak.
A szülőmappa `001_inventory_number_unique.sql` fájlja a korábbi üzleti adatbázis
külön, kézzel jóváhagyandó indexmigrációja. A két ágat **nem kell együtt futtatni**.
Nincs automatikusan induló migráció vagy adatjavítás.

1. `create_database.sql`: külön, autocommit adminisztratív lépés a `postgres`
   karbantartási adatbázison. Meglévő adatbázisnál hibázik, adatot nem cserél.
   Az idempotens, ellenőrzött változat: `scripts.prepare_inventory_database create`.
2. `001_create_inventory_items.sql`: a 11 oszlopos, kezelt szintetikus tábla.
3. `002_add_inventory_constraints.sql`: CHECK-ek és a leltári szám UNIQUE kulcsa.

A 001/002 egyenként egy atomikus `DO` utasítás. A Python `migrate` lépés együtt,
egyetlen tranzakcióban futtatja őket, majd ellenőrzi a teljes séma szerződését.
Újrafuttathatók; a névazonosság önmagában nem jogosít fel meglévő objektum átvételére.
A készlet betöltése külön parancs. Nincs DROP, DELETE, TRUNCATE vagy adatátmásolás.

Teljes, jóváhagyási feltételeket is tartalmazó útmutató:
[Tiszta tesztadatbázis](../../docs/clean_inventory_database.md).
