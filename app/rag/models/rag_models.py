from dataclasses import dataclass
from typing import Optional


@dataclass
class RagChunk:
    """Egy kereshető dokumentációs egység, mielőtt feltöltjük Qdrantba."""

    # Eszköz/item neve. Ebből lesz a payload.name mező, amelyet a HYBRID szűrők használnak.
    name: str
    # Dokumentációs szekció, például usage vagy troubleshooting.
    section: str
    # A tényleges szöveg, amelyből embedding készül, majd bekerül a RAG promptokba.
    text: str
    # Opcionális forrásfájl vagy dokumentumnév. Feltöltött PDF/TXT esetén segít a visszakeresett
    # kontextus azonosításában.
    source: Optional[str] = None
    # Dokumentumtípus, például "device_txt", "pdf" vagy "txt".
    doc_type: str = "device_txt"
    # Optional manufacturer provenance; old generic ingestion stays unchanged.
    item_code: Optional[str] = None
    source_url: Optional[str] = None
    source_sha256: Optional[str] = None
    page: Optional[int] = None
