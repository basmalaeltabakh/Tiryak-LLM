import re
from collections import Counter
from typing import Dict, List, Optional

from app.config import CHUNK_TARGET_TOKENS, CHUNK_MAX_TOKENS, CHUNK_OVERLAP_TOKENS
from app.embeddings.embedder import count_tokens, get_tokenizer

# Matches numbered section headings like "1.0 Introduction", "6.1 Antihypertensives",
# "6.1.1 When to consider stopping" (as used by the Polypharmacy guide, and a
# reasonable default for any similarly-structured generic upload).
_HEADING_RE = re.compile(r"^(\d+(?:\.\d+){0,3})\s+([A-Z].{0,90})$")
_PAGE_FOOTER_RE = re.compile(r"^page\s+\d+\s+of\s+\d+$", re.IGNORECASE)


def strip_boilerplate(pages_content: List[Dict]) -> List[Dict]:
    """
    Drops repeated running headers/footers (book title on every page, "Page
    N of NN" page counters) before chunking, so they don't pollute chunk
    text or dilute embeddings. A line counts as a "running header" if it
    appears verbatim on more than half the pages — this is a generic
    detector rather than a hardcoded string, so it works for any document
    fed through this generic parser, not just the Polypharmacy guide.
    """
    line_counts = Counter()
    for page in pages_content:
        lines = {l.strip() for l in page["text"].split("\n") if l.strip()}
        for line in lines:
            line_counts[line] += 1

    num_pages = max(len(pages_content), 1)
    running_headers = {line for line, count in line_counts.items() if count > num_pages / 2}

    cleaned_pages = []
    for page in pages_content:
        kept_lines = []
        for line in page["text"].split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped in running_headers or _PAGE_FOOTER_RE.match(stripped):
                continue
            kept_lines.append(line)
        cleaned_pages.append({"page_number": page["page_number"], "text": "\n".join(kept_lines)})
    return cleaned_pages


def _heading_depth(number: str) -> int:
    """
    "1.0"/"6.0" are chapter-level (depth 1); "6.1"/"6.2" are subsections of a
    chapter (depth 2); "6.1.1" is a sub-subsection (depth 3). Dot-count alone
    doesn't distinguish "6.0" from "6.1" (both have exactly one dot) — the
    tell is whether the second component is "0".
    """
    parts = number.split(".")
    if len(parts) == 1:
        return 1
    if len(parts) == 2:
        return 1 if parts[1] == "0" else 2
    return len(parts)


def _looks_like_toc_page(page_text: str) -> bool:
    """
    A table-of-contents page's entries are textually indistinguishable from
    real section headings (same "N.N Title" shape) — walking it as real
    content would seed the heading breadcrumb with a heading that's about to
    appear again, in order, everywhere else in the document, corrupting
    every subsequent section_title. Detected generically: a page where a
    large fraction of its non-empty lines are heading-shaped is almost
    certainly a contents/index page, not real body text.
    """
    lines = [l.strip() for l in page_text.split("\n") if l.strip()]
    if len(lines) < 5:
        return False
    heading_lines = sum(1 for l in lines if _HEADING_RE.match(l))
    return heading_lines >= 5 and heading_lines / len(lines) > 0.3


def split_into_sections(pages_content: List[Dict]) -> List[Dict]:
    """
    Walks the (boilerplate-stripped) pages looking for numbered headings and
    groups the text between them into sections, so a chunk boundary lands on
    a heading rather than mid-topic — this is what keeps a drug name together
    with its own risk/recommendation text instead of splitting them apart.
    Table-of-contents pages are skipped entirely (see _looks_like_toc_page).

    section_title is a breadcrumb of the active heading path (e.g.
    "6.1 Antihypertensives > 6.1.1 When to consider stopping"), truncated to
    the current heading's depth so a new "6.2" correctly drops the stale
    "6.1.1"/"6.1.2" trail. Falls back to a single "Overview" section if the
    document has no numbered headings at all (e.g. an unstructured upload).
    """
    sections: List[Dict] = []
    heading_stack: List[str] = []
    current: Optional[Dict] = None

    def flush():
        if current is not None and current["words"]:
            sections.append(current)

    for page in pages_content:
        if _looks_like_toc_page(page["text"]):
            continue

        page_number = page["page_number"]
        for raw_line in page["text"].split("\n"):
            line = raw_line.strip()
            if not line:
                continue

            match = _HEADING_RE.match(line)
            if match:
                depth = _heading_depth(match.group(1))
                heading_stack[depth - 1:] = [line]
                flush()
                current = {
                    "title": " > ".join(heading_stack),
                    "page_number": page_number,
                    "words": [],
                }
                continue

            if current is None:
                current = {"title": "Overview", "page_number": page_number, "words": []}
            current["words"].append(line)

    flush()
    return [{"title": s["title"], "page_number": s["page_number"], "text": " ".join(s["words"])} for s in sections]


def split_text_by_tokens(text: str, max_tokens: int, overlap_tokens: int) -> List[str]:
    """
    Splits text into pieces that fit within max_tokens, using the embedding
    model's own tokenizer (not a word-count estimate) so a chunk is never
    silently truncated at embed time. Only used as a fallback for the rare
    section that's too big to stand alone as one chunk.
    """
    tokenizer = get_tokenizer()
    token_ids = tokenizer.encode(text, add_special_tokens=False)
    if len(token_ids) <= max_tokens:
        return [text]

    pieces = []
    start = 0
    while start < len(token_ids):
        end = start + max_tokens
        piece_ids = token_ids[start:end]
        pieces.append(tokenizer.decode(piece_ids, skip_special_tokens=True))
        if end >= len(token_ids):
            break
        start = end - overlap_tokens
    return pieces


def _with_section_title_prefix(text: str, title: str) -> str:
    """
    Prepends "[section_title]" to the text that actually gets embedded, so
    the heading that disambiguates otherwise-similar sections (e.g.
    "Antidepressants > Withdrawal effects" vs "Benzodiazepines > Withdrawal
    effects" — same body-text shape, different drug class) becomes part of
    the embedded vector instead of living only in metadata the embedder
    never sees. A no-op if the text already opens with that exact prefix
    (aware_parser.py and hearts_parser.py's protocol sections already build
    their own "[Disease — Section]" prefix before handing text to the
    packer) — checked here rather than in each caller so every parser gets
    this for free without needing its own doubling guard.
    """
    prefix = f"[{title}]"
    return text if text.startswith(prefix) else f"{prefix}\n{text}"


def pack_sections_into_chunks(
    sections: List[Dict],
    target_tokens: int = CHUNK_TARGET_TOKENS,
    max_tokens: int = CHUNK_MAX_TOKENS,
    overlap_tokens: int = CHUNK_OVERLAP_TOKENS,
) -> List[Dict]:
    """
    Shared by all three document chunkers (this module, hearts_parser.py,
    aware_parser.py). Greedily merges consecutive same-source sections
    ({"title", "page_number", "text"}, in document order) into chunks up to
    ~target_tokens, WITHOUT ever splitting one section's text across a chunk
    boundary — a section only gets split (via split_text_by_tokens, with
    overlap) if it alone exceeds max_tokens. This is what keeps a
    recommendation, its dose, and its duration together: as long as they're
    captured as one section by the caller, packing never separates them.

    The returned "text" is prefixed with the chunk's section_title (see
    _with_section_title_prefix) — this is what gets embedded and stored;
    the section_title metadata field itself is untouched.

    Returns {"text", "section_title", "page_number"} dicts — page_number is
    the first page contributing to that chunk.
    """
    chunks: List[Dict] = []
    buffer_parts: List[str] = []
    buffer_title: Optional[str] = None
    buffer_page: Optional[int] = None
    buffer_tokens = 0

    def flush():
        if buffer_parts:
            chunks.append({
                "text": _with_section_title_prefix("\n\n".join(buffer_parts), buffer_title),
                "section_title": buffer_title,
                "page_number": buffer_page,
            })

    for section in sections:
        text = section["text"].strip()
        if not text:
            continue
        section_tokens = count_tokens(text)

        if section_tokens > max_tokens:
            flush()
            buffer_parts, buffer_title, buffer_page, buffer_tokens = [], None, None, 0
            for piece in split_text_by_tokens(text, max_tokens, overlap_tokens):
                chunks.append({
                    "text": _with_section_title_prefix(piece, section["title"]),
                    "section_title": section["title"],
                    "page_number": section["page_number"],
                })
            continue

        if buffer_parts and buffer_tokens + section_tokens > target_tokens:
            flush()
            buffer_parts, buffer_title, buffer_page, buffer_tokens = [], None, None, 0

        if not buffer_parts:
            buffer_title = section["title"]
            buffer_page = section["page_number"]
        buffer_parts.append(text)
        buffer_tokens += section_tokens

    flush()
    return chunks


def chunk_document(pages_content: List[Dict]) -> List[Dict]:
    """
    Generic section-aware, token-budgeted chunker. Strips repeated
    headers/footers, splits on numbered headings, then packs sections into
    ~CHUNK_TARGET_TOKENS chunks without breaking a section apart (see
    pack_sections_into_chunks). Produces the same chunk shape as before
    (chunk_id, text, page_number) plus a new section_title field.
    """
    cleaned_pages = strip_boilerplate(pages_content)
    sections = split_into_sections(cleaned_pages)
    packed = pack_sections_into_chunks(sections)

    chunks = []
    for i, chunk in enumerate(packed, start=1):
        chunks.append({
            "chunk_id": f"chunk_{i}",
            "text": chunk["text"],
            "page_number": chunk["page_number"],
            "section_title": chunk["section_title"],
        })
    return chunks
