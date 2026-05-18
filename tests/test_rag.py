from app.rag.retrieval.rag_service import answer_rag


def main():
    # Kézi füstteszt a teljes RAG válaszútvonalhoz. Embedding,
    # Qdrant adat és chat LLM hozzáférés szükséges hozzá.
    question = "How do I use a printer?"

    answer = answer_rag(question)

    print("\nANSWER:\n")
    print(answer)


if __name__ == "__main__":
    # Közvetlenül futtasd, ha terminálban szeretnéd megnézni a generált választ.
    main()
