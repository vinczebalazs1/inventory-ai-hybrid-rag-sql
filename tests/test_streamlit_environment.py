"""Exercise startup in a fresh process: cached clients must see the right env."""
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("has_dotenv", [True, False])
def test_streamlit_environment_before_client_initialization(tmp_path, has_dotenv):
    root = Path(__file__).resolve().parents[1]
    env_file = tmp_path / ".env"
    keys = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD",
            "QDRANT_URL", "QDRANT_API_KEY")
    inherited = ("old-host", "5433", "old-db", "old-user", "fake-old-password",
                 "https://old.example", "fake-old-key")
    current = ("current-host", "5432", "current-db", "current-user", "fake-new-password",
               "https://current.example", "fake-new-key")
    if has_dotenv:
        env_file.write_text("\n".join(f"{k}={v}" for k, v in zip(keys, current)), encoding="utf-8")
    expected = dict(zip(keys, current if has_dotenv else inherited))
    # The child has no imported application modules and no real service calls.
    code = r'''
import json, os, sys
from pathlib import Path
from unittest.mock import patch
import dotenv
from qdrant_client import QdrantClient
from streamlit.testing.v1 import AppTest

root, env_file = map(Path, sys.argv[1:3])
expected = json.loads(sys.argv[3])
original_load = dotenv.load_dotenv
local = QdrantClient(location=":memory:")
seen = []

def load_fixture(path=None, *args, **kwargs):
    if path is not None:
        assert Path(path) == root / ".env"
    return original_load(env_file, *args, **kwargs)

def make_client(*args, **kwargs):
    assert kwargs["url"] == expected["QDRANT_URL"]
    assert kwargs["api_key"] == expected["QDRANT_API_KEY"]
    seen.append(True)
    return local

with patch("dotenv.load_dotenv", side_effect=load_fixture), \
     patch("qdrant_client.QdrantClient", side_effect=make_client), \
     patch("openai.OpenAI", side_effect=AssertionError("Unexpected live AI client")):
    app = AppTest.from_file(str(root / "app/web/simple_server.py")).run(timeout=30)
    assert not app.exception, [e.message for e in app.exception]
    assert seen
    assert all(os.environ[k] == value for k, value in expected.items())
    assert any(b.label == "Run analysis" for b in app.button)
    from app.db.connection import get_connection
    with patch("psycopg2.connect") as connect:
        get_connection(connect_timeout=5)
        params = connect.call_args.kwargs
        for parameter, key in (("host", "DB_HOST"), ("port", "DB_PORT"),
                               ("dbname", "DB_NAME"), ("user", "DB_USER"),
                               ("password", "DB_PASSWORD")):
            assert params[parameter] == expected[key]
print("STARTUP_OK")
'''
    import json
    env = {**os.environ, **dict(zip(keys, inherited)), "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run(
        [sys.executable, "-B", "-c", code, str(root), str(env_file), json.dumps(expected)],
        cwd=root, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "STARTUP_OK" in result.stdout
