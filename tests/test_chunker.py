from app.rag.ingestion.parser import parse_devices
from app.rag.ingestion.chunker import chunk_all_devices


def main():
    
    with open("app/rag/data/devices.txt", "r", encoding="utf-8") as f:
        text = f.read()

  
    devices = parse_devices(text)

    chunks = chunk_all_devices(devices)

    print(f"\nTotal chunks: {len(chunks)}\n")


    for c in chunks[:10]:
        print(f"DEVICE: {c.name}")
        print(f"SECTION: {c.section}")
        print(f"TEXT PREVIEW: {c.text[:100]}...")
        print("-" * 50)


if __name__ == "__main__":
    main()