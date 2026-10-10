"""Keep test collection independent of the developer's Qdrant credentials."""
from unittest.mock import patch

from qdrant_client import QdrantClient

# Existing modules construct a Qdrant client at import time. Use its in-memory
# transport so collection and UI smoke tests never contact an external server.
with patch("qdrant_client.QdrantClient", return_value=QdrantClient(location=":memory:")):
    import app.rag.vector_store.qdrant_client  # noqa: F401


def pytest_addoption(parser):
    parser.addoption("--run-docling-pdf", action="store_true", default=False,
                     help="Run real PDF conversion; may download Docling models")
