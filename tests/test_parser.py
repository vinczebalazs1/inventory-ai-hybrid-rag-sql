from app.rag.ingestion.parser import parse_devices


def main():
    with open("app/rag/data/devices.txt", "r", encoding="utf-8") as f:
        text = f.read()

    devices = parse_devices(text)

    print("Parsed devices:\n")

    for d in devices:
        print("NAME:", d["name"])
        print("SECTIONS:", list(d["sections"].keys()))
        print("-" * 40)


if __name__ == "__main__":
    main()