# Három gyártói kézikönyv – kis HYBRID prototípus

A `manifest.json` a három ellenőrzött PDF URL-jét, SHA-256 értékét, modellnevét, cikkszámát és a kézzel átnézett részletek kiválasztását tartalmazza. Az oldalszám mindig **1-től számolt PDF-oldal**, nem a nyomtatott oldalcímke.

| Modell | Indexelendő PDF-oldalak/részletek | Kizárás |
|---|---|---|
| Dell P2422H | 6: biztonság; 33: Maintenance guidelines kezdetétől; 69–70: teljes önteszt | Más modellek specifikációi, állványváltozatok |
| Brother HL-L5200DW | 9: papírbetöltés; 11: kezdeti hibakeresés; 13: kizárólag No Paper bejegyzés | Régiós kellékanyagok és opcionális papírtálcák hibái |
| Epson EB-FH52 | 163–165: tisztítás/biztonság; 166: Cleaning the Air Filter and Vents és Replacing the Air Filter közötti rész | Modellfüggő karbantartási intervallumok és specifikációk |

A teljes PDF-ek csak helyileg, az ignorált `.cache/official_manuals/` könyvtárban vannak: `P2422H.pdf`, `HLL5200.pdf`, `EBFH52.pdf`. Új checkoutnál a jegyzék hivatalos URL-jeiről kell őket ide letölteni; a betöltő eltérő hash, hiányzó modelljelölés vagy nem egyértelmű szöveghatár esetén megáll. A PDF-eket és teljes kivonatukat ne add a Githez. A repository nem terjeszti a kézikönyveket.

Projektgyökérből (mindig új riportfájllal):

```powershell
venv\Scripts\python -B -m scripts.ingest_model_manuals --report evaluation/manual-dry-run.json
# Csak sikeres ellenőrzés és engedélyezett élő feltöltés esetén:
venv\Scripts\python -B -m scripts.ingest_model_manuals --apply --report evaluation/manual-apply.json
```

A dry-run a PDF-eket, a read-only `inventory_ai_clean` modellpárjait és a meglévő `devices` kollekciót ellenőrzi, embedding és írás nélkül. Apply esetén csak a hiányzó, külön névtérhez tartozó pontok kerülnek feltöltésre. Azonos pontokat kihagy, eltérő meglévő payloadot nem ír felül. Nincs automatikus teljes újrapróbálkozás. Hiba után a riportot és a távoli állapotot kell megvizsgálni.

A modellhez kötött HYBRID-hoz a SQL eredményének tényleges `name` és `item_code` oszlopai szükségesek. A generálási prompt ezt kéri, a visszakeresés pedig külön ellenőrzi. A nevek eredeti írásmódja megmarad. Hibás/hiányzó párnál vagy hiányzó dokumentációnál nincs szűretlen modell-fallback; a válasz ezt jelzi. A régi `devices.txt` a RAG ágban továbbra is kereshető, általános forrásként megjelölve.

Ez három modell néhány ellenőrzött fejezetének prototípusa. Nem fedi le a teljes kézikönyveket vagy a clean adatbázis összes modelljét. Későbbi tartalomfrissítésnél új hash és kézi alkalmazhatósági ellenőrzés szükséges; a régi dokumentumverziókat nem törli automatikusan.
