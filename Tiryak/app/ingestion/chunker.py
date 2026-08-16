import re
from typing import List, Dict
from app.config import CHUNK_SIZE, CHUNK_OVERLAP


def split_into_paragraphs(text: str) -> List[str]:
    """
    Splits raw text into paragraphs using blank lines as separators.
    Falls back to line-based splitting if no blank lines exist.
    """
    paragraphs = re.split(r"\n\s*\n", text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    if len(paragraphs) <= 1:
        # No blank-line separation found, split by single newlines instead
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

    return paragraphs


def split_long_paragraph(paragraph: str, chunk_size: int, overlap: int) -> List[str]:
    """
    Splits a paragraph that's too long into smaller overlapping chunks,
    breaking at word boundaries to avoid cutting words in half.
    """
    words = paragraph.split()
    chunks = []
    start = 0

    while start < len(words):
        end = start + chunk_size
        chunk_words = words[start:end]
        chunks.append(" ".join(chunk_words))
        start = end - overlap  # move forward but overlap a bit for context continuity

        if start <= 0:
            break

    return chunks


def chunk_document(pages_content: List[Dict],
                    chunk_size: int = CHUNK_SIZE,
                    overlap: int = CHUNK_OVERLAP) -> List[Dict]:
    """
    Converts parsed page content into a list of chunks ready for embedding.
    Groups paragraphs/lines together up to chunk_size words, instead of
    creating a separate chunk for every small paragraph or line.
    """
    all_chunks = []
    chunk_counter = 0

    for page in pages_content:
        page_number = page["page_number"]
        text = page["text"]

        if not text.strip():
            continue

        paragraphs = split_into_paragraphs(text)

        current_chunk_words = []
        current_word_count = 0

        for paragraph in paragraphs:
            paragraph_words = paragraph.split()
            para_word_count = len(paragraph_words)

            # If a single paragraph alone is bigger than chunk_size,
            # flush what we have, then split it on its own
            if para_word_count > chunk_size:
                if current_chunk_words:
                    chunk_counter += 1
                    all_chunks.append({
                        "chunk_id": f"chunk_{chunk_counter}",
                        "text": " ".join(current_chunk_words),
                        "page_number": page_number
                    })
                    current_chunk_words = []
                    current_word_count = 0

                sub_chunks = split_long_paragraph(paragraph, chunk_size, overlap)
                for sub_chunk in sub_chunks:
                    chunk_counter += 1
                    all_chunks.append({
                        "chunk_id": f"chunk_{chunk_counter}",
                        "text": sub_chunk,
                        "page_number": page_number
                    })
                continue

            # If adding this paragraph would exceed chunk_size, flush first
            if current_word_count + para_word_count > chunk_size and current_chunk_words:
                chunk_counter += 1
                all_chunks.append({
                    "chunk_id": f"chunk_{chunk_counter}",
                    "text": " ".join(current_chunk_words),
                    "page_number": page_number
                })

                # Start new chunk with overlap: keep the tail words of the previous chunk
                overlap_words = current_chunk_words[-overlap:] if overlap < len(current_chunk_words) else current_chunk_words
                current_chunk_words = overlap_words[:]
                current_word_count = len(current_chunk_words)

            current_chunk_words.extend(paragraph_words)
            current_word_count += para_word_count

        # Flush whatever remains at the end of the page
        if current_chunk_words:
            chunk_counter += 1
            all_chunks.append({
                "chunk_id": f"chunk_{chunk_counter}",
                "text": " ".join(current_chunk_words),
                "page_number": page_number
            })

    return all_chunks