from dataclasses import dataclass


@dataclass
class RagChunk:
    name: str
    section: str
    text: str