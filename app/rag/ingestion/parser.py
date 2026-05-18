import re
from typing import List, Dict


# Támogatott szekciónevek, amelyeket minden eszközblokkból ki akarunk nyerni.
SECTION_NAMES = ["description", "usage", "troubleshooting", "notes"]


def parse_devices(text: str) -> List[Dict]:
    """
    Nyers TXT input parse-olása strukturált eszköz objektumokká.

    Elvárt input formátum példa:
        === DEVICE: Printer ===
        Description: ...
        Usage: ...
        Troubleshooting: ...
        Notes: ...

    Visszatérés:
        Dictionary-k listája ilyen formában:
        [
            {
                "name": "printer",
                "sections": {
                    "description": "...",
                    "usage": "...",
                    ...
                }
            }
        ]
    """

    devices = []

    # Az input szöveget eszközblokkokra bontjuk az eszköz delimiter alapján.
    # Az első splitelt rész lehet üres szöveg az első device marker előtt.
    blocks = re.split(r"=== DEVICE:", text)

    for block in blocks:
        block = block.strip()

        # Üres blokkok kihagyása, például az első delimiter előtti rész.
        if not block:
            continue

        # Eszköznév kinyerése a headerből.
        # Példa header: "Printer ===\nDescription:..."
        header_match = re.match(r"(.*?)===", block, re.DOTALL)

        # Ha a header formátuma hibás, kihagyjuk ezt a blokkot.
        if not header_match:
            continue

        # Eszköznév normalizálása: kisbetűsítés és trim.
        # Ugyanez a kisbetűs név kerül később a Qdrant payload.name mezőbe.
        raw_name = header_match.group(1).strip()
        name = raw_name.lower()

        # A header utáni maradék tartalom kinyerése.
        content = block[header_match.end():].strip()

        # Szekciók parse-olása: description, usage stb.
        sections = parse_sections(content)

        # Strukturált eszközadat eltárolása.
        devices.append({
            "name": name,
            "sections": sections
        })

    return devices


def parse_sections(text: str) -> Dict[str, str]:
    """
    Előre definiált szekciók kinyerése egy eszközblokkból.

    Felismert szekciók:
        Description:
        Usage:
        Troubleshooting:
        Notes:

    Visszatérés:
        Dictionary, amely szekcióneveket köt össze a tartalmukkal.
    """

    sections = {}

    for section in SECTION_NAMES:
        # Minden ismert szekciót a következő ismert szekció headerig
        # vagy az eszközblokk végéig fogunk meg.
        # Regex magyarázat:
        # - "SectionName:" illesztése.
        # - Minden szöveg megfogása a következő szekcióig vagy a szöveg végéig.
        pattern = rf"{section.capitalize()}:(.*?)(?=(Description|Usage|Troubleshooting|Notes):|$)"

        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)

        if match:
            # Kinyert tartalom tisztítása.
            content = match.group(1).strip()

            # Csak a nem üres szekciókat tároljuk.
            if content:
                sections[section] = content

    return sections
