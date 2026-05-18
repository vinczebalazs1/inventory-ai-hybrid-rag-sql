from app.rag.retrieval.retriever import retrieve_semantic, retrieve_by_name


def main():
    # Kézi visszakeresési füstteszt. Meglévő Qdrant collection adat kell hozzá.
    print("\n=== SEMANTIC SEARCH ===\n")

    results = retrieve_semantic("How to use a printer?")

    for r in results:
        # A válaszcsomagnak ugyanazokat a kulcsokat kell tartalmaznia, amelyeket ingestionkor mentünk.
        print(r["name"], "|", r["section"])
        print(r["text"][:100])
        print("-" * 50)

    print("\n=== FILTERED SEARCH ===\n")

    results = retrieve_by_name("printer", "How to use it?")

    for r in results:
        # A szűrt keresésnek csak olyan chunkokat kell visszaadnia, ahol a payload.name=printer.
        print(r["name"], "|", r["section"])
        print(r["text"][:100])
        print("-" * 50)


if __name__ == "__main__":
    # Közvetlenül futtasd a tág semantic search és a név szerinti keresés összehasonlításához.
    main()
