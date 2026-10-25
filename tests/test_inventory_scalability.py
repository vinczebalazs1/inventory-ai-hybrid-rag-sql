"""10k rows and concurrent repeat seeding on a second disposable cluster."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter
import os

import psycopg2
from test_matching_postgres import isolated_postgres
from app.test_data.artifacts import source_hashes, write_json
from app.test_data.database import ConnectionConfig, TARGET, create_database, migrate, load_dataset, verify_dataset
from app.test_data.generator import generate
from app.test_data.models import GenerationConfig
from app.record_matching.config import MatchingSettings
from app.record_matching.repository import InventoryRepository
from app.services.schema_service import load_schema


def test_10000_rows_concurrent_import_and_exact_lookup(isolated_postgres, tmp_path):
    connection = isolated_postgres()
    dsn = connection.get_dsn_parameters()
    connection.close()
    params = {key: dsn[key] for key in ("host", "port", "user")}
    config = ConnectionConfig(TARGET, params["user"], "unused", params["host"], int(params["port"]))
    def connect():
        return psycopg2.connect(**params, dbname=TARGET, connect_timeout=5)
    create_database(config, apply=True, confirm_db=TARGET, connection_factory=isolated_postgres)
    migrate(config, apply=True, confirm_db=TARGET, connection_factory=connect)
    generation = GenerationConfig(count=10000)
    started = perf_counter()
    rows = generate(generation)
    generation_ms = (perf_counter() - started) * 1000
    def load():
        return load_dataset(config, rows, generation, apply=True, confirm_db=TARGET, connection_factory=connect)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: load(), range(2)))
    assert sorted(r["status"] for r in outcomes) == ["already_loaded", "loaded"]
    verified = verify_dataset(config, rows, generation, connection_factory=connect)
    assert verified["validation_passed"] and verified["record_count"] == 10000
    columns = {c["column"]: c["type"] for c in load_schema()["inventory_items"]}
    search = InventoryRepository(connect).search({"inventory_number": "L-09999"}, columns,
                                                MatchingSettings(max_candidates=1, max_scan_rows=1))
    assert search.metadata.complete and search.metadata.scanned_rows == 1
    report = {"environment": "isolated PostgreSQL, concurrent loaders, single run; not a general performance guarantee",
        "count": len(rows), "generation_ms": generation_ms, "load_outcomes": outcomes,
        "verification": verified, "exact_lookup_ms": search.metadata.duration_ms,
        "implementation_sha256": source_hashes()[0]}
    write_json(Path(os.getenv("CLEAN_INVENTORY_REPORT_DIR", str(tmp_path))) / "scalability.json", report)
