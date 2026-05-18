from app.services.routing_service import route_query


def main():
    # Kézi füstteszt az LLM útvonalválasztóhoz. OPENAI_API_KEY szükséges hozzá.
    questions = [
        "Where is the printer?",
        "How do I use a printer?",
        "Where is the printer and how to use it?",
    ]

    for q in questions:
        print(f"Q: {q}")
        print(f"ROUTE: {route_query(q)}")
        print("-" * 40)


if __name__ == "__main__":
    # Közvetlenül futtasd pytest helyett, mert élő útvonalválasztó döntéseket ír ki.
    main()
