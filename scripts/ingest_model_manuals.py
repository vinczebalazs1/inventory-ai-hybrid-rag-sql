"""Reviewed PDFs only. Default: dry-run. --apply explicitly enables embedding/upload."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        parser.error("Report already exists; use a new report path")
    from app.rag.manuals import load_manifest, prepare_chunks, index_manual_chunks
    from app.db.connection import get_connection
    from app.rag.vector_store.qdrant_client import client, COLLECTION
    report = {"status": "started", "embedding_attempts": 0, "embedding_successes": 0,
              "embedding_tokens": 0, "automatic_retries": 0}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    def save():
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    save()
    try:
        docs = load_manifest()
        chunks = prepare_chunks(docs)
        conn = get_connection(connect_timeout=10)
        try:
            conn.set_session(readonly=True, isolation_level="REPEATABLE READ")
            with conn.cursor() as cur:
                cur.execute("SELECT current_database(), current_setting('transaction_read_only')")
                if cur.fetchone() != ("inventory_ai_clean", "on"):
                    raise ValueError("Expected read-only inventory_ai_clean")
                for doc in docs:
                    cur.execute("SELECT DISTINCT name, item_code FROM public.inventory_items WHERE name=%s OR item_code=%s",
                                (doc["name"], doc["item_code"]))
                    if cur.fetchall() != [(doc["name"], doc["item_code"])]:
                        raise ValueError("Database does not confirm manifest model identity")
        finally:
            conn.rollback()
            conn.close()
        if COLLECTION != "devices":
            raise ValueError("Expected devices collection")
        embedder = None
        if args.apply:
            from app.rag.embedding import embedding_service as embedding
            if embedding.MODEL != "text-embedding-3-large":
                raise ValueError("Unexpected embedding model")
            provider = embedding._get_client().with_options(max_retries=0, timeout=45)
            def embedder(text):
                report["embedding_attempts"] += 1
                save()
                response = provider.embeddings.create(model=embedding.MODEL, input=text)
                report["embedding_successes"] += 1
                report["embedding_tokens"] += response.usage.total_tokens
                save()
                return response.data[0].embedding
        report.update(index_manual_chunks(client, COLLECTION, chunks, apply=args.apply, embedder=embedder))
        report["status"] = "passed"
    except Exception as exc:
        # Do not persist credentials, provider bodies or connection strings.
        report.update(status="stopped_on_error", error_type=type(exc).__name__)
        raise SystemExit(1) from None
    finally:
        save()
        client.close()
        print(json.dumps({k: v for k, v in report.items() if k != "points"}, ensure_ascii=True))


if __name__ == "__main__":
    main()
