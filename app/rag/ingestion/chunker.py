from typing import List, Dict
from app.rag.models.rag_models import RagChunk


def chunk_device(device: Dict) -> List[RagChunk]:
    """
    Convert a parsed device into chunk objects.

    Input:
    {
        "name": "printer",
        "sections": {
            "description": "...",
            "usage": "...",
            ...
        }
    }

    Output:
    [
        RagChunk(name="printer", section="usage", text="..."),
        ...
    ]
    """

    name = device["name"]
    sections = device.get("sections", {})

    chunks = []

    for section_name, content in sections.items():
        content = content.strip()

        if not content:
            continue

        chunks.append(
            RagChunk(
                name=name,
                section=section_name,
                text=content
            )
        )

    return chunks


def chunk_all_devices(devices: List[Dict]) -> List[RagChunk]:
    """
    Process all parsed devices into a flat list of chunks.
    """

    all_chunks = []

    for device in devices:
        device_chunks = chunk_device(device)
        all_chunks.extend(device_chunks)

    return all_chunks