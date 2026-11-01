import re
from typing import Any


def split_text(text: str, chunk_size: int = 1200, chunk_overlap: int = 200) -> list[str]:
    """Split markdown text into semantic chunks while preserving code blocks.

    Strategy:
    1. Extracts fenced code blocks (```...```) as atomic units to prevent breaking code syntax.
    2. Splits surrounding prose into paragraphs by double newlines.
    3. Breaks down any unit that exceeds chunk_size into smaller line/word segments.
    4. Packs units into chunks up to chunk_size, carrying forward chunk_overlap bytes.
    """
    units: list[str] = []
    pattern = re.compile(r"```[\s\S]*?```")
    last_position = 0

    for match in pattern.finditer(text):
        preceding_text = text[last_position:match.start()]
        paragraphs = re.split(r"\n\s*\n", preceding_text)
        units.extend(p.strip() for p in paragraphs if p.strip())

        units.append(match.group().strip())
        last_position = match.end()

    remaining_text = text[last_position:]
    units.extend(p.strip() for p in re.split(r"\n\s*\n", remaining_text) if p.strip())

    processed_units: list[str] = []
    for unit in units:
        if unit.startswith("```") and unit.endswith("```"):
            processed_units.append(unit)
            continue

        if len(unit) <= chunk_size:
            processed_units.append(unit)
            continue

        current_lines: list[str] = []
        current_length = 0

        for line in unit.splitlines():
            if len(line) > chunk_size:
                if current_lines:
                    processed_units.append("\n".join(current_lines))
                    current_lines = []
                    current_length = 0

                words = line.split()
                current_word_chunk = ""
                for word in words:
                    if len(current_word_chunk) + len(word) + 1 > chunk_size:
                        if current_word_chunk:
                            processed_units.append(current_word_chunk)
                        current_word_chunk = word
                    else:
                        current_word_chunk = f"{current_word_chunk} {word}".strip()

                if current_word_chunk:
                    processed_units.append(current_word_chunk)

            elif current_lines and current_length + len(line) + 1 > chunk_size:
                processed_units.append("\n".join(current_lines))
                current_lines = [line]
                current_length = len(line)
            else:
                current_lines.append(line)
                current_length += len(line) + 1

        if current_lines:
            processed_units.append("\n".join(current_lines))

    chunks: list[str] = []
    current_chunk: list[str] = []

    for unit in processed_units:
        current_length = len("\n\n".join(current_chunk))

        if current_chunk and current_length + len(unit) + 2 > chunk_size:
            chunks.append("\n\n".join(current_chunk))

            overlap: list[str] = []
            overlap_length = 0
            for previous in reversed(current_chunk):
                additional_length = len(previous) + 2
                if (
                    overlap_length + additional_length <= chunk_overlap
                    and overlap_length + additional_length + len(unit) + 2 <= chunk_size
                ):
                    overlap.insert(0, previous)
                    overlap_length += additional_length
                else:
                    break
            current_chunk = overlap

        current_chunk.append(unit)

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks


def chunk_documents(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert loaded documents into indexed chunk dictionaries with metadata."""
    all_chunks: list[dict[str, Any]] = []

    for document in documents:
        text_chunks = split_text(document["content"])
        for index, chunk in enumerate(text_chunks):
            all_chunks.append({
                "id": f"{document['metadata']['source']}_{index}",
                "content": chunk,
                "metadata": {
                    **document["metadata"],
                    "chunk_id": index,
                },
            })

    return all_chunks
