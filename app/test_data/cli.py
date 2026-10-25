"""Shared CLI parsing/reporting; no changes to the application's environment."""
import argparse
from pathlib import Path
import json

from .artifacts import export_dataset, read_bundle, write_json
from .database import (CleanDatabaseError, ConnectionConfig, create_database, load_dataset,
                       migrate, verify_dataset)
from .models import GenerationConfig


def main(command: str, argv=None) -> int:
    parser = argparse.ArgumentParser(description=f"InventoryAI szintetikus tesztadatok: {command}")
    parser.add_argument("--report", type=Path, help="JSON-riport célfájlja")
    if command == "generate":
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--count", type=int, default=1000)
        parser.add_argument("--output", type=Path, default=Path("data/synthetic"))
        parser.add_argument("--locations", nargs="+", help="Helyszínek, szóközzel elválasztva")
        parser.add_argument("--documents", action="store_true", help="16 forgatókönyv, PDF és DOCX; fejlesztői függőségekkel")
    else:
        parser.add_argument("--env-file", type=Path, default=Path(".env.clean.local"))
        if command == "prepare":
            parser.add_argument("stage", choices=("create", "migrate"))
        else:
            parser.add_argument("--dataset", type=Path, default=Path("data/synthetic"))
            parser.add_argument("--expected-count", type=int, default=1000)
        if command in ("prepare", "load"):
            parser.add_argument("--apply", action="store_true", help="Írás engedélyezése a megerősített célba")
            parser.add_argument("--confirm-db", help="Íráskor pontosan inventory_ai_clean")
        if command == "load":
            parser.add_argument("--batch-size", type=int, default=250)
        if command == "evaluate":
            parser.add_argument("--postgres", action="store_true", help="Valódi, csak olvasó clean PostgreSQL; alapértelmezés offline")
    args = parser.parse_args(argv)
    try:
        if command == "generate":
            config = GenerationConfig(seed=args.seed, count=args.count, **({"locations": tuple(args.locations)} if args.locations else {}))
            if args.documents and (config.count < 1000 or "KANDÓ" not in config.locations):
                raise CleanDatabaseError("A dokumentumcsomaghoz legalább 1000 rekord és KANDÓ helyszín szükséges.")
            report = export_dataset(args.output, config)
            if args.documents:
                from .documents import export_documents
                rows, _, _ = read_bundle(args.output, expected_count=config.count)
                export_documents(args.output, rows, report)
                report = json.loads((args.output / "manifest.json").read_text(encoding="utf-8"))
            report = {"status": "generated", **report}
        else:
            config = None if command == "evaluate" and not args.postgres else ConnectionConfig.from_env(args.env_file)
            if command == "prepare":
                operation = create_database if args.stage == "create" else migrate
                report = operation(config, apply=args.apply, confirm_db=args.confirm_db)
            else:
                rows, generation, manifest = read_bundle(args.dataset, expected_count=args.expected_count)
                if command == "load":
                    report = load_dataset(config, rows, generation, apply=args.apply,
                                          confirm_db=args.confirm_db, batch_size=args.batch_size)
                elif command == "verify":
                    report = verify_dataset(config, rows, generation)
                elif command == "evaluate":
                    from .documents import read_ground_truth
                    from .evaluation import evaluate
                    repository = None
                    if args.postgres:
                        verification = verify_dataset(config, rows, generation)
                        if not verification["validation_passed"]:
                            raise CleanDatabaseError("Az adatbázis nem egyezik a dokumentumok adatkészletével.")
                        from app.record_matching.repository import InventoryRepository
                        repository = InventoryRepository(config.connect)
                    report = evaluate(rows, read_ground_truth(args.dataset, manifest), repository=repository,
                                      mode="postgres" if args.postgres else "offline")
                else:
                    raise ValueError("Unknown command")
        failed = report.get("validation_passed") is False or report.get("failed", 0) > 0
        code = 1 if failed else 0
        summary = "Eltérés található; nézd át a riportot." if failed else "Az ellenőrzött művelet befejeződött."
    except Exception as exc:
        # Provider/driver errors may contain DSNs, credentials or submitted content.
        report = {"status": "error", "exception_type": type(exc).__name__, "validation_passed": False,
                  "message": str(exc) if isinstance(exc, CleanDatabaseError) else
                  "A művelet nem fejeződött be. Ellenőrizd a konfigurációt, a készletet és a hozzáférést; részleges import nem marad."}
        code, summary = 1, report["message"]
    if args.report:
        write_json(args.report, report)
    console = {k: v for k, v in report.items() if k not in
               ("source_manifest", "cases", "quality", "settings", "files")} if args.report else report
    print(json.dumps(console, ensure_ascii=False, indent=2))
    print(summary)
    return code
