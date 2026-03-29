from app.rag.ingestion.ingestion_service import ingest_devices


def main():
    ingest_devices("app/rag/data/devices.txt")


if __name__ == "__main__":
    main()