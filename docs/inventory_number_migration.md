# Leltári szám: adatbázis-audit és UNIQUE migráció

## Aktuális állapot — 2026-10-17

Az audit a tényleges `public.inventory_items` táblán, `READ ONLY`,
`REPEATABLE READ` tranzakcióban futott. Az üzleti adatbázison nem történt módosítás.

| Ellenőrzés | Eredmény |
|---|---:|
| Tábla és elvárt 11 oszlop | Elérhető, kompatibilis |
| `inventory_number` adattípusa | `text` |
| Teljes, érvényes UNIQUE / PRIMARY KEY | Nincs |
| Összes sor | 1000 |
| Duplikált, nem NULL leltári szám | 8 csoport, 16 sor |
| NULL / üres / csak whitespace | 0 / 0 / 0 |
| Whitespace-t tartalmazó érték | 0 |
| Csak whitespace/kisbetűsítés után ütköző különböző érték | 0 |

Duplikációk: `L-16912`, `L-17256`, `L-17758`, `L-36622`, `L-45143`,
`L-54305`, `L-66423`, `L-88949`; mindegyik kétszer szerepel.
A [gépi riport](../evaluation/results/inventory_number_audit.json) tartalmazza
az érintett cikkszámot, alszámot, nevet, helyszínt és aktiválási dátumot is.
Az audit teljes darabszámokat számol; a részletes minták korlátozottak, a
korlát miatti levágást külön jelzi. A mostani 8 csoport és 16 sor teljesen belefért.

**A jelenlegi adatokra a UNIQUE migráció nem alkalmazható.** A leltári számokat
eredeti leltárbizonylatokkal kell ellenőrizni. A riport nem dönti el, melyik sor
helyes, és nem ad automatikus törlési, összevonási vagy átszámozási parancsot.
A minták üzleti adatokat tartalmaznak; publikált szakdolgozati melléklethez anonimizálás szükséges.

## Mi számít valódi garanciának?

A jelenlegi duplikációmentesség önmagában nem adatbázis-garancia. A matcher minden
kereséskor a katalógusból ellenőrzi az indexet: teljes, egyszerű oszlopokon működő,
érvényes, kész és azonnali UNIQUE/PRIMARY KEY kell. Részleges vagy `lower(...)`
kifejezéses indexet nem kezel teljes leltáriszám-kulcsként.

A meglévő üzleti kulcs elegendő: nem készítünk új `id`/UUID mezőt.
A hagyományos UNIQUE több NULL értéket megenged; ilyen sorokhoz nem lesz
leltáriszám-alapú azonosság. `NOT NULL` bevezetése külön üzleti döntés.
A kis-/nagybetűs és whitespace-eltérések diagnosztikai csoportosítása nem módosít
adatot, nem keresési normalizáló szabály és nem azonosít két külön tárolt kulcsot.

## Fájlok és végrehajtási mód

- [001_inventory_number_unique.sql](../migrations/001_inventory_number_unique.sql)
- [001_inventory_number_unique_rollback.sql](../migrations/001_inventory_number_unique_rollback.sql)

A migráció a vizsgált 1000 soros táblához **tranzakciós `CREATE UNIQUE INDEX`**
megoldást használ. A `SHARE` tábla-zár az előellenőrzés idejére is kizárja az
új írásokat. A szokásos olvasás tovább működhet. Az egész módosítás `BEGIN` / `COMMIT`
között történik; hiba esetén az új index is visszagördül. Nincs automatikus
érvénytelen-index-törlés, adatjavítás vagy más adatbázisobjektum eltávolítása.
Az írókat érintő rövid karbantartási ablakot egyeztetni kell.

A `CREATE INDEX CONCURRENTLY` nem futtatható tranzakcióblokkban, és sikertelen
építés után érvénytelen index maradhat. Ezért ebben a tranzakciós migrációban
**nem használjuk**, és a fájlban nem szabad egyszerűen erre átírni a parancsot.
Nagy, folyamatosan írt táblára külön, jóváhagyott concurrent migráció és annak
hibakezelése szükséges. [PostgreSQL CREATE INDEX dokumentáció](https://www.postgresql.org/docs/18/sql-createindex.html),
[zárolási módok](https://www.postgresql.org/docs/18/explicit-locking.html).

Előellenőrzések: megfelelő tábla és szöveges oszlop; nincs öröklés/RLS;
nincs nem NULL duplikáció vagy üres leltári szám; meglévő megfelelő index
újrahasználata; ütköző index-/objektumnév esetén biztonságos leállás.
A névegyezés nem helyettesíti az index definíciójának vizsgálatát.
`lock_timeout=5s`, `statement_timeout=60s`; az időtúllépés nem oldható meg vak újrapróbálással.

## Jóváhagyás utáni alkalmazás

1. Futtasd a friss auditot:

   ```powershell
   venv\Scripts\python -m scripts.audit_inventory_numbers --output evaluation/results/inventory_number_audit.json
   ```

   A CLI kilépési kódja 1, ha a migráció blokkolt vagy az audit sikertelen;
   a JSON megkülönbözteti ezeket. Sikertelen kapcsolódásból nincs kitalált audit.

2. Az illetékes adatgazda ellenőrizze és rendezze a duplikációkat az eredeti
   bizonylatok alapján. Ez a fejlesztés nem végez ilyen üzleti módosítást.
3. Ismételd meg az auditot; nézd át a NULL és normalizálási figyelmeztetéseket is.
   Ellenőrizd a mentést, a céladatbázist és az index létrehozásához szükséges jogosultságot.
4. Kérj **explicit jóváhagyást** erre a konkrét migrációra és a karbantartási ablakra.
   A mostani fejlesztési feladat nem adott engedélyt az üzleti migráció alkalmazására.
5. A jóváhagyás után, a megfelelő adatbázisnevet/felhasználót behelyettesítve:

   ```powershell
   psql -X -W -h localhost -U "ADATBAZIS_FELHASZNALO" -d "ADATBAZIS_NEVE" -v ON_ERROR_STOP=1 -f migrations/001_inventory_number_unique.sql
   ```

   A jelszót a promptban add meg. Hiba esetén a `psql` leáll; a megszakadt
   tranzakciót ne próbáld részletekben folytatni. A parancs nem része az alkalmazás
   indulásának vagy bármely Streamlit-gombnak.
6. Futtasd újra az auditot. Az `inventory_unique_verified=true` az elvárt eredmény.
   Ezután új egyeztetést indíts; a korábbi Streamlit eredmény munkamenetben tárolt pillanatkép.
7. Egy ismert leltári számú dokumentumon ellenőrizd az EXACT eredményt, a
   `inventory_number_exact` stratégiát és a kihagyott fuzzy keresést.

## Visszaállítás

Külön jóváhagyás után ugyanazzal a `psql` kapcsolattal a
`001_inventory_number_unique_rollback.sql` fájl futtatható. Csak a migráció
megjelölésével ellátott, megfelelő táblán és oszlopon levő indexet törli.
Más néven már létező indexet nem távolít el. Idegen/eltérő objektumnál leáll;
függőséget nem töröl (`CASCADE` nincs). Adatsorok nem változnak. A garancia
eltávolítása után a matcher ismét ellenőrizendő, nem garantált találatokat ad.

## Ellenőrzés

Az izolált PostgreSQL-tesztek igazolták a duplikáció miatti leállást,
a meglévő és INCLUDE-os UNIQUE újrahasználatát, az idempotenciát, a több NULL
megengedését, a névütközés elutasítását, az üres kulcs blokkolását és a
megjelöléshez kötött visszaállítást. A tényleges üzleti adatbázison csak az audit futott.
