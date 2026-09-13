from typing import List


def chunk_text(
    text: str,
    max_chars: int = 12000,
    overlap: int = 500,
) -> List[str]:
    """
    Split long text into semantically useful chunks.

    Strategy:
    1. Prefer paragraph boundaries.
    2. Preserve a small overlap between chunks.
    3. Hard-split oversized paragraphs.
    4. Never return empty chunks.
    """
    text = (text or "").strip()

    if not text:
        return []

    if len(text) <= max_chars:
        return [text]

    paragraphs = [
        paragraph.strip()
        for paragraph in text.split("\n\n")
        if paragraph.strip()
    ]

    chunks: List[str] = []
    current = ""

    for paragraph in paragraphs:
        # Handle a paragraph larger than max_chars.
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""

            start = 0
            while start < len(paragraph):
                end = min(start + max_chars, len(paragraph))
                piece = paragraph[start:end].strip()

                if piece:
                    chunks.append(piece)

                if end >= len(paragraph):
                    break

                start = max(0, end - overlap)

            continue

        candidate = (
            f"{current}\n\n{paragraph}"
            if current
            else paragraph
        )

        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current.strip())

            previous_overlap = current[-overlap:] if current else ""
            current = (
                f"{previous_overlap}\n\n{paragraph}"
                if previous_overlap
                else paragraph
            )

            # Safety split if overlap caused the chunk to exceed the limit.
            if len(current) > max_chars:
                chunks.append(current[:max_chars].strip())
                current = current[max_chars - overlap:]

    if current.strip():
        chunks.append(current.strip())

    return chunks


def progressively_smaller_chunks(
    text: str,
    sizes=(12000, 8000, 6000, 4000),
    overlap: int = 300,
) -> List[List[str]]:
    """
    Produce progressively smaller chunk sets for 413 recovery.
    """
    return [
        chunk_text(text, max_chars=size, overlap=overlap)
        for size in sizes
        if text
    ]