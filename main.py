from app.orchestration.orchestrator import handle_question


def main():
    # Minimális CLI belépési pont ugyanannak a feldolgozási láncnak a kipróbálásához Streamlit nélkül.
    question = input("Kerdes: ")

    try:
        # A CLI és a webes UI ugyanazt az orchestrator hívást használja,
        # ezért a működésnek egyeznie kell, csak a megjelenítés más.
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

        if response.get("sources"):
            print("\n--- SOURCES ---")
            for i, source in enumerate(response["sources"], start=1):
                confidence = source.get("confidence")
                confidence_text = f"{confidence}%" if confidence is not None else "-"
                print(f"[{i}] {source.get('source')} | {source.get('section')} | {confidence_text}")

        print("\n--- NATURAL LANGUAGE ANSWER ---")
        print(response["answer"])

    except Exception as e:
        print("\nHiba tortent:")
        print(e)


if __name__ == "__main__":
    # Így futtatható közvetlenül: python main.py
    main()
