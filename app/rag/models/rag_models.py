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
