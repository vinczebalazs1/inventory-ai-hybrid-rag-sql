"""Exact HU/EN field labels; never fuzzy-match asset identifiers or values."""
import re
import unicodedata


def label_key(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value.casefold())
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in folded if not unicodedata.combining(c)))


LABELS = {
    label_key(label): target
    for target, labels in {
        "inventory_number": ("leltári szám", "leltári azonosító", "inventory number", "inventory id"),
        "item_code": ("cikkszám", "tételkód", "item code"),
        "sub_code": ("alszám", "altételkód", "sub code"),
        "name": ("eszköz neve", "eszköz megnevezése", "megnevezés", "device name", "asset name"),
        "location": ("hely", "helyszín", "helyazonosító", "nyilvántartott hely", "location"),
        "activation_date": ("aktiválás dátuma", "aktiválási dátum", "üzembe helyezés dátuma", "activation date"),
        "purchase_value": ("beszerzési érték", "bekerülési érték", "purchase value"),
        "depreciation": ("értékcsökkenés", "elszámolt értékcsökkenés", "felhalmozott écs", "depreciation"),
        "current_value": ("jelenlegi érték", "nettó könyv szerinti érték", "current value"),
        "quantity": ("mennyiség", "darabszám", "quantity"),
        "currency": ("pénznem", "currency"),
    }.items() for label in (target, *labels)
}


def canonical_label(value: str) -> str | None:
    return LABELS.get(label_key(value))
