"""Environment settings, following the existing dotenv configuration."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_ARTIFACTS_PATH = Path(__file__).resolve().parents[2] / ".cache" / "docling"


@dataclass(frozen=True)
class Settings:
    chunk_size: int = 12000
    chunk_overlap: int = 500
    mapping_batch_size: int = 80
    model: str = "gpt-6-luna"
    target_table: str = "inventory_items"
    max_file_bytes: int = 25 * 1024 * 1024
    max_pages: int = 200
    debug_json_bytes: int = 200000
    artifacts_path: str | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.chunk_overlap < self.chunk_size:
            raise ValueError("Require 0 <= overlap < chunk size")
        if min(self.mapping_batch_size, self.max_file_bytes, self.max_pages) <= 0:
            raise ValueError("Processing limits must be positive")

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(
            chunk_size=int(os.getenv("DOCUMENT_CHUNK_SIZE", "12000")),
            chunk_overlap=int(os.getenv("DOCUMENT_CHUNK_OVERLAP", "500")),
            mapping_batch_size=int(os.getenv("DOCUMENT_MAPPING_BATCH_SIZE", "80")),
            model=os.getenv("DOCUMENT_LLM_MODEL", "gpt-6-luna"),
            target_table=os.getenv("DOCUMENT_TARGET_TABLE", "inventory_items"),
            artifacts_path=os.getenv("DOCUMENT_ARTIFACTS_PATH") or (
                str(DEFAULT_ARTIFACTS_PATH) if (DEFAULT_ARTIFACTS_PATH / ".ready").is_file() else None
            ),
        )
