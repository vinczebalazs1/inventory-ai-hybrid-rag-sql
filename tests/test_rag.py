from app.rag.retrieval.rag_service import answer_rag


def main():
    question = "How do I use a printer?"

    answer = answer_rag(question)

    print("\nANSWER:\n")
    print(answer)


if __name__ == "__main__":
    main()