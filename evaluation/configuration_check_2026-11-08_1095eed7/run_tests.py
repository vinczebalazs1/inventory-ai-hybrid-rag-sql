"""Run existing tests without external HTTP or live database connections."""
import contextlib
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")

import httpx
import psycopg2
import pytest
import requests


def forbidden(*args, **kwargs):
    raise AssertionError("External HTTP and real database connections are disabled in this test run")


if __name__ == "__main__":
    attempt = OUT / "tests_attempt_02"
    attempt.mkdir(exist_ok=False)
    temporary = ROOT / ".cache/configuration_checks" / OUT.name / "pytest_tmp"
    temporary.parent.mkdir(parents=True, exist_ok=True)
    arguments = ["-q", "-p", "no:cacheprovider", "--run-docling-pdf",
                 "--junitxml=" + str(attempt / "test_results.xml"),
                 "--basetemp=" + str(temporary)]
    with (attempt / "pytest.log").open("w", encoding="utf-8") as log:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            with patch.object(httpx.Client, "send", forbidden), \
                 patch.object(httpx.AsyncClient, "send", forbidden), \
                 patch.object(requests.Session, "request", forbidden), \
                 patch.object(psycopg2, "connect", forbidden):
                code = pytest.main(arguments)
    (attempt / "pytest_exit_code.json").write_text(json.dumps({"exit_code": int(code), "arguments": arguments,
        "external_http_blocked": True, "live_database_connections_blocked": True,
        "postgres_opt_in_enabled": False}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"exit_code": int(code), "log": str(attempt / "pytest.log")}))
    raise SystemExit(code)
