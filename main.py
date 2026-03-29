from app.orchestration.orchestrator import handle_question


def main():
    question = input("Kerdes: ")

    try:
        response = handle_question(question)

        print("\n--- ROUTE ---")
        print(response["route"])

        if response["sql"]:
            print("\n--- SAFE SQL ---")
            print(response["sql"])

        print("\n--- STRUCTURED RESULT ---")
        print(response["result"])

        if response.get("matched_names"):
            print("\n--- MATCHED NAMES ---")
            print(response["matched_names"])

        print("\n--- NATURAL LANGUAGE ANSWER ---")
        print(response["answer"])

    except Exception as e:
        print("\nHiba tortent:")
        print(e)


if __name__ == "__main__":
    main()
