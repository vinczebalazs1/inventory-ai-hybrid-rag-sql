from app.orchestration.orchestrator import handle_question


def main():
    question = input("Kérdés: ")

    try:
        response = handle_question(question)

        print("\n--- SAFE SQL ---")
        print(response["sql"])

        print("\n--- STRUCTURED RESULT ---")
        print(response["result"])

        print("\n--- NATURAL LANGUAGE ANSWER ---")
        print(response["answer"])

    except Exception as e:
        print("\n❌ Hiba történt:")
        print(e)


if __name__ == "__main__":
    main()