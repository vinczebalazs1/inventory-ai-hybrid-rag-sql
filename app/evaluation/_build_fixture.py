"""One-time authoring helper for the frozen, manually labelled fixture."""
import json
from pathlib import Path

cases = []


def case(identifier, category, description, doc, records, truth=(), status="EXACT_MATCH",
         actions=("ATTACH_DOCUMENT",), review=False, deltas=(), unique=None,
         uncertain=False, evaluable=True, search="complete", types=None, unmapped=None):
    document_fields = [{"field": key, "value": value} for key, value in doc.items()] if isinstance(doc, dict) else doc
    cases.append({
        "id": identifier, "split": "calibration" if identifier.startswith("C") else "test",
        "category": category, "description": description, "document_fields": document_fields,
        "records": [{"record_id": key, "values": values} for key, values in records.items()],
        "unique_keys": [["item_code"]] if unique is None else unique,
        "schema_types": types or {}, "search_status": search, "unmapped_fields": unmapped or [],
        "expected": {"record_ids": list(truth), "match_status": status, "actions": list(actions),
                     "review_required": review, "uncertain": uncertain, "identity_evaluable": evaluable,
                     "deltas": [{"record_id": rid, "field": field} for rid, field in deltas]},
    })


REVIEW = ("MANUAL_REVIEW",)
NEW = ("CREATE_RECORD_CANDIDATE", "MANUAL_REVIEW")
UPDATE = ("ATTACH_DOCUMENT", "UPDATE_CANDIDATE", "MANUAL_REVIEW")

# Calibration examples are separate from the final test split. No optimization
# code is run on either split; these cases document policy-level expectations.
case("C01", "exact", "Egyedi leltári szám; minden dokumentummező egyezik.",
     {"inventory_number": "LAB-001", "name": "Brother HL-L2372DN"},
     {"r1": {"item_code": "C-PR", "inventory_number": "LAB-001", "name": "Brother HL-L2372DN"}},
     ["r1"], unique=[["inventory_number"]])
case("C02", "item_code", "Csak igazoltan egyedi cikkszám áll rendelkezésre.",
     {"item_code": "CAL-ROUTER"}, {"r1": {"item_code": "CAL-ROUTER", "name": "MikroTik hAP ax3"}}, ["r1"])
case("C03", "composite_description", "Név és telephely alapján valószínű, de nem bizonyított azonosság.",
     {"name": " DELL   Latitude 5540 ", "location": "Budapest"},
     {"r1": {"item_code": "C-LAP", "name": "Dell Latitude 5540", "location": "Budapest"}},
     ["r1"], "LIKELY_MATCH", REVIEW, True)
case("C04", "sparse", "Önmagában az általános eszköznév nem elég az azonosításhoz.",
     {"name": "Monitor"}, {"r1": {"item_code": "C-MON", "name": "Monitor"}},
     ["r1"], "INSUFFICIENT_DATA", REVIEW, True, uncertain=True)
case("C05", "new", "Üres szintetikus leltár, új azonosító és eszköznév.",
     {"item_code": "CAL-NEW", "name": "Epson EB-FH52", "location": "Szeged"}, {},
     status="NO_MATCH", actions=NEW, review=True)
case("C06", "duplicate_identifier", "Két külön sor osztozik ugyanazon nem egyedi leltári számon.",
     {"inventory_number": "DUP-CAL", "name": "Office display"},
     {"r1": {"item_code": "A", "inventory_number": "DUP-CAL", "name": "Office display"},
      "r2": {"item_code": "B", "inventory_number": "DUP-CAL", "name": "Office display"}},
     ["r2"], "AMBIGUOUS_MATCH", REVIEW, True, uncertain=True)
case("C07", "typo", "Egy karakter elírás a névben, a helyszín egyezik.",
     {"name": "Lenovo ThinkPqd T14", "location": "Győr"},
     {"r1": {"item_code": "L14", "name": "Lenovo ThinkPad T14", "location": "Győr"}},
     ["r1"], "LIKELY_MATCH", REVIEW, True, deltas=[("r1", "name")])
case("C08", "identifier_conflict", "Leltári szám és cikkszám két külön rekordra mutat.",
     {"inventory_number": "C-INV-1", "item_code": "C-ITEM-2"},
     {"r1": {"item_code": "C-ITEM-1", "inventory_number": "C-INV-1"},
      "r2": {"item_code": "C-ITEM-2", "inventory_number": "C-INV-2"}},
     ["r1"], "CONFLICTING_DATA", REVIEW, True, uncertain=True)
case("C09", "schema_failure", "A séma audit meghiúsul; ez nem bizonyít új rekordot.",
     {"item_code": "CAL-SCHEMA", "name": "Router"}, {}, status="ERROR", actions=REVIEW,
     review=True, uncertain=True, search="schema_mismatch")
case("C10", "multiple_entities", "Két külön leltári szám a lapos dokumentummezőkben.",
     [{"field": "inventory_number", "value": "ONE"}, {"field": "inventory_number", "value": "TWO"}],
     {}, status="CONFLICTING_DATA", actions=REVIEW, review=True, uncertain=True, evaluable=False)

case("T01", "exact", "Egyedi cikkszám és pontos eszközleírás egy másik modell mellett.",
     {"item_code": "IT-100", "name": "HP EliteBook 840 G10", "location": "Pécs"},
     {"r1": {"item_code": "IT-100", "name": "HP EliteBook 840 G10", "location": "Pécs"},
      "r2": {"item_code": "IT-101", "name": "HP EliteBook 850 G10", "location": "Pécs"}}, ["r1"])
case("T02", "identifier_trim", "Az azonosító körüli szóközök eltávolíthatók, a tartalma megmarad.",
     {"inventory_number": " INV-00500 "},
     {"r1": {"item_code": "PROJECTOR", "inventory_number": "INV-00500", "name": "Optoma HD146X"}},
     ["r1"], unique=[["inventory_number"]])
case("T03", "composite_key", "Cikkszám önmagában nem egyedi, az alábontási kóddal együtt igazolt kulcs.",
     {"item_code": "BUNDLE", "sub_code": 2, "name": "Dell P2422H"},
     {"r1": {"item_code": "BUNDLE", "sub_code": 1, "name": "Dell P2422H"},
      "r2": {"item_code": "BUNDLE", "sub_code": 2, "name": "Dell P2422H"}},
     ["r2"], unique=[["item_code", "sub_code"]])
case("T04", "location_delta", "Pontos azonosító mellett költözött az eszköz; helyszínfrissítés ellenőrzendő.",
     {"item_code": "MOVE-1", "name": "Canon i-SENSYS MF445dw", "location": "Debrecen"},
     {"r1": {"item_code": "MOVE-1", "name": "Canon i-SENSYS MF445dw", "location": "Budapest"}},
     ["r1"], actions=UPDATE, review=True, deltas=[("r1", "location")])
case("T05", "quantity_delta", "A mennyiség változott, miközben a rekordazonosító biztos.",
     {"item_code": "CHAIR-PACK", "name": "Irodai szék", "quantity": 6},
     {"r1": {"item_code": "CHAIR-PACK", "name": "Irodai szék", "quantity": 4}},
     ["r1"], actions=UPDATE, review=True, deltas=[("r1", "quantity")])
case("T06", "money_delta", "Egy fillérnyi pontos decimális eltérés sem veszhet el.",
     {"item_code": "FIN-01", "name": "Fluke 117", "purchase_value": "123456789012345.68"},
     {"r1": {"item_code": "FIN-01", "name": "Fluke 117", "purchase_value": "123456789012345.67"}},
     ["r1"], actions=UPDATE, review=True, deltas=[("r1", "purchase_value")], types={"purchase_value": "numeric"})
case("T07", "decimal_equivalence", "Eltérő decimális skála ugyanazt a pénzértéket fejezi ki.",
     {"item_code": "FIN-02", "purchase_value": "1200.00", "currency": "EUR"},
     {"r1": {"item_code": "FIN-02", "purchase_value": "1200.0", "currency": "EUR"}},
     ["r1"], types={"purchase_value": "numeric"})
case("T08", "date_delta", "Érvényes ISO dátumok egy nap eltéréssel.",
     {"item_code": "DATE-01", "activation_date": "2024-02-29"},
     {"r1": {"item_code": "DATE-01", "activation_date": "2024-02-28"}},
     ["r1"], actions=UPDATE, review=True, deltas=[("r1", "activation_date")])
case("T09", "unicode", "Unicode összetett és felbontott ékezet, valamint whitespace különbség.",
     {"item_code": "UNI-1", "name": "  Me\u0301rőműszer   X200 ", "location": " GYŐR "},
     {"r1": {"item_code": "UNI-1", "name": "Mérőműszer X200", "location": "Győr"}}, ["r1"])
case("T10", "typo", "Névbeli karaktercsere, egyező helyszín és üzembe helyezési dátum.",
     {"name": "Lenovo ThinkPad T41 Gen 4", "location": "Sopron", "activation_date": "2025-01-15"},
     {"r1": {"item_code": "T14-01", "name": "Lenovo ThinkPad T14 Gen 4", "location": "Sopron", "activation_date": "2025-01-15"}},
     ["r1"], "CONFLICTING_DATA", REVIEW, True, uncertain=True)
case("T11", "word_order", "Szavak sorrendje változott, a modellazonosító megmaradt.",
     {"name": "P2422H Dell Monitor", "location": "Veszprém"},
     {"r1": {"item_code": "DISP-22", "name": "Dell Monitor P2422H", "location": "Veszprém"}},
     ["r1"], "LIKELY_MATCH", REVIEW, True, deltas=[("r1", "name")])
case("T12", "model_numbers", "5540 és 5550 külön modell; magas névhasonlóság nem bizonyít azonosságot.",
     {"name": "Dell Latitude 5540", "location": "Eger"},
     {"r1": {"item_code": "D-5550", "name": "Dell Latitude 5550", "location": "Eger"}},
     status="CONFLICTING_DATA", actions=REVIEW, review=True, uncertain=True)
case("T13", "ambiguous", "Azonos név és helyszín mellett két külön fizikai eszköz.",
     {"name": "Samsung S24R350", "location": "Baja"},
     {"r1": {"item_code": "S-1", "name": "Samsung S24R350", "location": "Baja"},
      "r2": {"item_code": "S-2", "name": "Samsung S24R350", "location": "Baja"}},
     ["r2"], "AMBIGUOUS_MATCH", REVIEW, True, uncertain=True)
case("T14", "location_disambiguation", "Azonos típus, két város; helyszín csak kiegészítő bizonyíték.",
     {"name": "Zebra ZD421", "location": "Nyíregyháza"},
     {"r1": {"item_code": "Z-A", "name": "Zebra ZD421", "location": "Nyíregyháza"},
      "r2": {"item_code": "Z-B", "name": "Zebra ZD421", "location": "Kaposvár"}},
     ["r1"], "LIKELY_MATCH", REVIEW, True)
case("T15", "date_disambiguation", "Név és aktiválási dátum alapján elkülöníthető beszerzések.",
     {"name": "Cisco Catalyst C1000", "activation_date": "2025-06-10"},
     {"r1": {"item_code": "SW-OLD", "name": "Cisco Catalyst C1000", "activation_date": "2022-06-10"},
      "r2": {"item_code": "SW-NEW", "name": "Cisco Catalyst C1000", "activation_date": "2025-06-10"}},
     ["r2"], "LIKELY_MATCH", REVIEW, True)
case("T16", "identifier_conflict", "Mindkét létező azonosító külön rekordhoz tartozik.",
     {"item_code": "CAM-A", "inventory_number": "INV-CAM-B", "name": "Sony Alpha A6400"},
     {"r1": {"item_code": "CAM-A", "inventory_number": "INV-CAM-A", "name": "Sony Alpha A6400"},
      "r2": {"item_code": "CAM-B", "inventory_number": "INV-CAM-B", "name": "Sony Alpha A6400"}},
     ["r1"], "CONFLICTING_DATA", REVIEW, True, uncertain=True)
case("T17", "identifier_technical_conflict", "Pontos leltári szám mellett más gyártó és modell szerepel.",
     {"item_code": "MIX-1", "name": "HP ProBook 450"},
     {"r1": {"item_code": "MIX-1", "name": "Dell Latitude 7440"}},
     ["r1"], "CONFLICTING_DATA", REVIEW, True, uncertain=True)
case("T18", "leading_zero", "Az INV-00125 nem olvadhat össze az INV-125 azonosítóval.",
     {"inventory_number": "INV-00125", "name": "Brother ADS-1700W", "location": "Szolnok"},
     {"r1": {"item_code": "OLD-SCAN", "inventory_number": "INV-125", "name": "BenQ GW2480", "location": "Miskolc"}},
     status="NO_MATCH", actions=NEW, review=True)
case("T19", "identifier_case", "Azonosító kisbetűje nem normalizálható nagybetűvé üzleti szabály nélkül.",
     {"item_code": "rack-a", "name": "Synology DS923", "location": "Szeged"},
     {"r1": {"item_code": "RACK-A", "name": "APC Smart UPS 1500", "location": "Budapest"}},
     status="NO_MATCH", actions=NEW, review=True)
case("T20", "punctuation_identifier", "A kötőjel az azonosító része, nem dobható el.",
     {"item_code": "A-12", "name": "Logitech Brio 500", "location": "Tata"},
     {"r1": {"item_code": "A12", "name": "Canon EOS R50", "location": "Paks"}},
     status="NO_MATCH", actions=NEW, review=True)
case("T21", "new_empty", "Teljes keresés üres leltárban, elegendő új rekordadat.",
     {"inventory_number": "NEW-2026-1", "name": "Bosch GLM 50-27", "location": "Dunaújváros", "quantity": 1},
     {}, status="NO_MATCH", actions=NEW, review=True)
case("T22", "new_unrelated_inventory", "Új eszköz meglévő, eltérő kategóriájú leltárrekordok mellett.",
     {"item_code": "MIC-NEW", "name": "Rode NT-USB", "location": "Békéscsaba"},
     {"r1": {"item_code": "DESK-1", "name": "Irodai íróasztal", "location": "Békéscsaba"},
      "r2": {"item_code": "VAC-2", "name": "Karcher WD3", "location": "Szeged"}},
     status="NO_MATCH", actions=NEW, review=True)
case("T23", "sparse_new", "Csak új cikkszám alapján nem indokolt teljes újrekord-javaslat.",
     {"item_code": "UNKNOWN-ONLY"}, {}, status="NO_MATCH", actions=REVIEW, review=True, uncertain=True)
case("T24", "empty_document", "Nincs kinyert dokumentummező.", {}, {},
     status="INSUFFICIENT_DATA", actions=REVIEW, review=True, uncertain=True)
case("T25", "nonidentifying_fields", "Ár és pénznem önmagában nem rekordazonosító.",
     {"purchase_value": 100000, "currency": "HUF"},
     {"r1": {"item_code": "PRICE-1", "name": "Dell P2723D", "purchase_value": 100000, "currency": "HUF"}},
     ["r1"], "INSUFFICIENT_DATA", REVIEW, True, uncertain=True)
case("T26", "document_conflict", "Ugyanaz a célséma mező két eltérő cikkszámot kapott.",
     [{"field": "item_code", "value": "DOC-A"}, {"field": "item_code", "value": "DOC-B"},
      {"field": "name", "value": "LG 27UP650"}], {},
     status="CONFLICTING_DATA", actions=REVIEW, review=True, uncertain=True, evaluable=False)
case("T27", "repeated_equal_field", "Ismétlődő, de azonos értékű mezők nem jelentenek két eszközt.",
     [{"field": "item_code", "value": "REPEAT-1"}, {"field": "item_code", "value": "REPEAT-1"},
      {"field": "name", "value": "Philips 243V7"}],
     {"r1": {"item_code": "REPEAT-1", "name": "Philips 243V7"}}, ["r1"])
case("T28", "multi_entity_name", "Két eszköz neve, egyetlen lapos mezőlista; nincs rekordcsoportosítás.",
     [{"field": "name", "value": "Dell U2723QE"}, {"field": "name", "value": "HP LaserJet M404"},
      {"field": "location", "value": "Budapest"}], {},
     status="CONFLICTING_DATA", actions=REVIEW, review=True, uncertain=True, evaluable=False)
case("T29", "invalid_identifier", "A kritikus azonosító előző normalizálása hibás volt.",
     [{"field": "inventory_number", "value": None, "raw": "???", "invalid": True},
      {"field": "name", "value": "Epson L3250"}, {"field": "location", "value": "Pécs"}],
     {"r1": {"item_code": "EPS-1", "name": "Epson L3250", "location": "Pécs"}},
     ["r1"], "INSUFFICIENT_DATA", REVIEW, True, uncertain=True)
case("T30", "invalid_quantity", "Érvényes cikkszám mellett hibás mennyiség nem válhat módosítássá.",
     [{"field": "item_code", "value": "BAD-QTY"}, {"field": "quantity", "value": None, "raw": "kettő", "invalid": True}],
     {"r1": {"item_code": "BAD-QTY", "name": "TP-Link TL-SG108", "quantity": 2}},
     ["r1"], actions=("ATTACH_DOCUMENT", "MANUAL_REVIEW"), review=True)
case("T31", "missing_evidence", "A kinyert azonosítóhoz nincs forrásidézet; nincs automatikus elfogadás.",
     [{"field": "item_code", "value": "NO-EVID", "evidence": None}, {"field": "name", "value": "Acer Vero B247"}],
     {"r1": {"item_code": "NO-EVID", "name": "Acer Vero B247"}},
     ["r1"], "INSUFFICIENT_DATA", REVIEW, True, uncertain=True)
case("T32", "database_null", "Adatbázis NULL helyszín ismeretlen érték, nem tényleges eltérés.",
     {"item_code": "NULL-LOC", "location": "Kecskemét"},
     {"r1": {"item_code": "NULL-LOC", "location": None}}, ["r1"])
case("T33", "document_null", "Explicit üres dokumentummező nem jelent SQL NULL-ra törlési utasítást.",
     [{"field": "item_code", "value": "DOC-NULL"}, {"field": "location", "value": None, "raw": ""}],
     {"r1": {"item_code": "DOC-NULL", "location": "Salgótarján"}},
     ["r1"], actions=("ATTACH_DOCUMENT", "MANUAL_REVIEW"), review=True)
case("T34", "omitted_document_field", "Hiányzó helyszín és értékmezők a dokumentumban nem törlendők.",
     {"item_code": "OMIT-1"},
     {"r1": {"item_code": "OMIT-1", "location": "Tatabánya", "current_value": 42000, "quantity": 1}}, ["r1"])
case("T35", "partial_search", "Kandidánskorlát miatt csonkolt keresésből nem lehet új rekordra következtetni.",
     {"item_code": "LIMIT-NEW", "name": "Fujitsu ScanSnap iX1600", "location": "Mór"}, {},
     status="SEARCH_INCOMPLETE", actions=REVIEW, review=True, uncertain=True, search="partial")
case("T36", "partial_exact", "A részleges keresés akkor is jelzendő, ha egy pontos rekord látszik.",
     {"item_code": "LIMIT-EXACT", "name": "Dymo LabelWriter 550"},
     {"r1": {"item_code": "LIMIT-EXACT", "name": "Dymo LabelWriter 550"}},
     ["r1"], "SEARCH_INCOMPLETE", REVIEW, True, uncertain=True, search="partial")
case("T37", "database_error", "Adatbázis elérési hiba nem NO_MATCH.",
     {"item_code": "OFFLINE-1", "name": "Asus ExpertBook B1"}, {},
     status="ERROR", actions=REVIEW, review=True, uncertain=True, search="error")
case("T38", "timeout", "Időtúllépés után nincs újrekord-javaslat.",
     {"item_code": "TIMEOUT-1", "name": "Yealink T54W"}, {},
     status="SEARCH_INCOMPLETE", actions=REVIEW, review=True, uncertain=True, search="timeout")
case("T39", "sql_injection_text", "Azonosítóba írt SQL töredék egyszerű adat; nem egyezik normál kulccsal.",
     {"item_code": "x' OR 1=1 --", "name": "A dokumentumban szereplő külön tétel", "location": "Szeged"},
     {"r1": {"item_code": "NORMAL-1", "name": "HP ZBook Firefly 14", "location": "Pécs"}},
     status="NO_MATCH", actions=NEW, review=True)
case("T40", "serial_semantics", "Service Tag nem belső leltári szám, még azonos karakterek esetén sem.",
     {}, {"r1": {"item_code": "SVC-1", "inventory_number": "ST123456", "name": "Dell OptiPlex 7010"}},
     ["r1"], "INSUFFICIENT_DATA", REVIEW, True, uncertain=True,
     unmapped=[{"label": "Service Tag", "value": "ST123456"}])
case("T41", "unstable_identity", "Nincs igazolt egyedi kulcs; egy látható egyezés nem biztos rekordazonosítás.",
     {"item_code": "NO-KEY", "name": "NEC MultiSync EA241F"},
     {"r1": {"item_code": "NO-KEY", "name": "NEC MultiSync EA241F"}},
     ["r1"], "LIKELY_MATCH", REVIEW, True, unique=[], uncertain=True)
case("T42", "same_model_multiple_ids", "Azonos leltári szám két fizikai eszközön, eltérő stabil kulcsokkal.",
     {"inventory_number": "DUP-INV-42", "name": "LG 24MP400"},
     {"r1": {"item_code": "LG-A", "inventory_number": "DUP-INV-42", "name": "LG 24MP400"},
      "r2": {"item_code": "LG-B", "inventory_number": "DUP-INV-42", "name": "LG 24MP400"}},
     ["r2"], "AMBIGUOUS_MATCH", REVIEW, True, uncertain=True)
case("T43", "different_description", "Pontos kulcs mellett kisbetűsítés nem értékeltérés.",
     {"item_code": "TXT-CASE", "name": "epson eb-w06", "location": " budapest "},
     {"r1": {"item_code": "TXT-CASE", "name": "EPSON EB-W06", "location": "Budapest"}}, ["r1"])
case("T44", "multi_delta", "Egy rekord több független, validált mezőeltéréssel.",
     {"item_code": "DELTA-44", "name": "APC Back UPS 650", "location": "Siófok", "quantity": 2,
      "current_value": 15000, "currency": "EUR"},
     {"r1": {"item_code": "DELTA-44", "name": "APC Back UPS 650", "location": "Keszthely", "quantity": 1,
             "current_value": 25000, "currency": "HUF"}},
     ["r1"], actions=UPDATE, review=True,
     deltas=[("r1", "location"), ("r1", "quantity"), ("r1", "current_value"), ("r1", "currency")])
case("T45", "simple_typo", "Betűhiba a gyártónévben, változatlan modell és helyszín.",
     {"name": "Logitehc MX Master 3", "location": "Zalaegerszeg"},
     {"r1": {"item_code": "MOUSE-45", "name": "Logitech MX Master 3", "location": "Zalaegerszeg"},
      "r2": {"item_code": "MOUSE-46", "name": "Microsoft Sculpt", "location": "Zalaegerszeg"}},
     ["r1"], "LIKELY_MATCH", REVIEW, True, deltas=[("r1", "name")])
case("T46", "no_location", "Pontos eszköznév és dátum, helyszín nélkül.",
     {"name": "Elgato Stream Deck MK2", "activation_date": "2025-09-03"},
     {"r1": {"item_code": "DECK-1", "name": "Elgato Stream Deck MK2", "activation_date": "2025-09-03"}},
     ["r1"], "LIKELY_MATCH", REVIEW, True)
case("T47", "unsupported_serial_mapping", "Hibás korábbi mapping: Serial Number címkét inventory_number mezőbe soroltak.",
     [{"field": "inventory_number", "value": "SER-7788", "label": "Serial Number"},
      {"field": "name", "value": "Dell Precision 3580"}],
     {"r1": {"item_code": "SERIAL-47", "inventory_number": "SER-7788", "name": "Dell Precision 3580"}},
     ["r1"], "CONFLICTING_DATA", REVIEW, True, uncertain=True)
case("T48", "near_tie", "Két hasonló nevű kandidáns ugyanazon helyszínen; a kis eltérés nem döntő.",
     {"name": "Dell Professional Monitor P24", "location": "Esztergom"},
     {"r1": {"item_code": "NEAR-A", "name": "Dell Professional Monitor P24 A", "location": "Esztergom"},
      "r2": {"item_code": "NEAR-B", "name": "Dell Professional Monitor P24 B", "location": "Esztergom"}},
     ["r2"], "AMBIGUOUS_MATCH", REVIEW, True, uncertain=True)

dataset = {
    "version": 1,
    "description": "Kézzel tervezett szintetikus rekordegyeztetési esetek; nem valós üzleti adatok. Az elvárt kimenetek előzetes policy-címkék.",
    "split_policy": "10 kalibrációs és 48 külön teszteset. A küszöbök nem optimalizáltak ezekre az esetekre; a végső mérést a test halmazon kell értelmezni.",
    "cases": cases,
}
if __name__ == "__main__":
    destination = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "matching_evaluation.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(cases)} manually labelled cases to {destination}")
