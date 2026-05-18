from app.rag.ingestion.ingestion_service import ingest_devices


def main():
    # Kézi ingestion füstteszt. Ez vektorokat ír Qdrantba.
    ingest_devices("app/rag/data/devices.txt")


if __name__ == "__main__":
    # Közvetlenül futtasd, ha újra akarod építeni a vektor indexet.
    main()
