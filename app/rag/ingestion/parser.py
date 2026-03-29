import re
from typing import List, Dict


# Supported section names we want to extract from each device block
SECTION_NAMES = ["description", "usage", "troubleshooting", "notes"]


def parse_devices(text: str) -> List[Dict]:
    """
    Parse raw TXT input into structured device objects.

    Expected input format example:
        === DEVICE: Printer ===
        Description: ...
        Usage: ...
        Troubleshooting: ...
        Notes: ...

    Returns:
        A list of dictionaries like:
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

    # Split the input text into device blocks using the device delimiter
    blocks = re.split(r"=== DEVICE:", text)

    for block in blocks:
        block = block.strip()

        # Skip empty blocks (can happen before the first delimiter)
        if not block:
            continue

        # Extract device name from the header
        # Example header: "Printer ===\nDescription:..."
        header_match = re.match(r"(.*?)===", block, re.DOTALL)

        # If header format is invalid, skip this block
        if not header_match:
            continue

        # Normalize device name (lowercase, trimmed)
        raw_name = header_match.group(1).strip()
        name = raw_name.lower()

        # Extract the remaining content after the header
        content = block[header_match.end():].strip()

        # Parse sections (description, usage, etc.)
        sections = parse_sections(content)

        # Store structured device data
        devices.append({
            "name": name,
            "sections": sections
        })

    return devices


def parse_sections(text: str) -> Dict[str, str]:
    """
    Extract predefined sections from a device block.

    Recognized sections:
        Description:
        Usage:
        Troubleshooting:
        Notes:

    Returns:
        A dictionary mapping section names to their content.
    """

    sections = {}

    for section in SECTION_NAMES:
        # Regex explanation:
        # - Match "SectionName:"
        # - Capture everything until the next section or end of text
        pattern = rf"{section.capitalize()}:(.*?)(?=(Description|Usage|Troubleshooting|Notes):|$)"

        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)

        if match:
            # Clean extracted content
            content = match.group(1).strip()

            # Only store non-empty sections
            if content:
                sections[section] = content

    return sections