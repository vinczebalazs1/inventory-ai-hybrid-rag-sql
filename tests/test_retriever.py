from app.rag.retrieval.retriever import retrieve_semantic, retrieve_by_name


def main():
    print("\n=== SEMANTIC SEARCH ===\n")

    results = retrieve_semantic("How to use a printer?")

    for r in results:
        print(r["name"], "|", r["section"])
        print(r["text"][:100])
        print("-" * 50)

    print("\n=== FILTERED SEARCH ===\n")

    results = retrieve_by_name("printer", "How to use it?")

    for r in results:
        print(r["name"], "|", r["section"])
        print(r["text"][:100])
        print("-" * 50)


if __name__ == "__main__":
    main()