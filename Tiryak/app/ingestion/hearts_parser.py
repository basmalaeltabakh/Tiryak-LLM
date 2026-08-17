"""
Parser for the WHO HEARTS Technical Package (evidence-based treatment
protocols for cardiovascular disease in primary care).

Most of this 43-page document is ordinary linear prose (Introduction,
Diabetes detection and treatment, Identifying emergencies, Annex) — that
part reuses the same boilerplate-stripping and heading-detection helpers as
the generic chunker (app/ingestion/chunker.py), same as any other report-
style document.

The 10 treatment protocols (9 hypertension + 1 diabetes) are different: each
is a one-page infographic combining a step-by-step flowchart (step 1 -> 7),
a side panel ("Provision for Specific Patients" / "Lifestyle Management
Advice"), and a "Drugs and Doses" grid table — three visually distinct
regions verified via PyMuPDF block coordinates, not assumed. Several
protocols are also preceded by a "Box N: Advantages and disadvantages of
<drug class>" page. Both need dedicated extraction so a chunk never
separates a flowchart step from the dose table it leads to.
"""

import re
from typing import Dict, List, Optional

import fitz

from app.ingestion.chunker import (
    pack_sections_into_chunks,
    split_into_sections,
    strip_boilerplate,
)

_PROTOCOL_HEADER_LINE = {"hypertension protocol", "diabetes protocol"}
_BOX_HEADER_RE = re.compile(r"^Box\s*\d+\s*:\s*(.+)$", re.IGNORECASE)
_STEP_RE = re.compile(r"^step\s*(\d*)\W*$", re.IGNORECASE)
_DRUGS_AND_DOSES_RE = re.compile(r"drugs\s+and\s+doses", re.IGNORECASE)
_FOOTNOTE_START_RE = re.compile(r"^[*†¥§#]")

# Side-panel content sits right of this x-fraction of the page width; the
# step flowchart sits left of it. Verified against real protocol pages:
# step-column blocks land around x=20-300, panel blocks around x=365-580 on
# a 595pt-wide page (~0.6 of page width) — well clear of either region.
_PANEL_X_FRACTION = 0.6


# Same font-subset defect as the AWaRe PDF (see aware_parser.py): "fi"/"fl"
# sometimes extract as the proper Unicode ligature glyph (ﬁ/ﬂ) and sometimes
# as plain ASCII, inconsistently, for what is conceptually the same text
# (e.g. a protocol's title block vs. a second occurrence of that title
# elsewhere on the page). Left unnormalized, two extractions of the "same"
# string compare unequal, which silently broke the "is this block the title
# block, skip it" dedup check in _extract_protocol_page.
_LIGATURE_MAP = str.maketrans({"ﬁ": "fi", "ﬂ": "fl"})


def _clean_text(text: str) -> str:
    text = text.translate(_LIGATURE_MAP)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _block_lines(block_text: str) -> List[str]:
    return [_clean_text(l) for l in block_text.split("\n") if _clean_text(l)]


def _has_protocol_header_line(block_text: str) -> bool:
    """
    True only if some LINE in this block is exactly "HYPERTENSION PROTOCOL"
    or "DIABETES PROTOCOL" (case-insensitive) — deliberately NOT a substring
    search, since e.g. the overview page's prose ("...sample hypertension
    protocols have been endorsed...") contains "hypertension protocol" as a
    substring of "protocols" without being the actual page header.
    """
    return any(line.lower() in _PROTOCOL_HEADER_LINE for line in _block_lines(block_text))


def _page_protocol_title(blocks) -> Optional[str]:
    """Returns the protocol's display title if this page is a protocol-flow page, else None."""
    for b in blocks:
        if _has_protocol_header_line(b[4]):
            lines = _block_lines(b[4])
            # The header block is "<kind> PROTOCOL" optionally followed by the
            # title on the next line; the title sometimes lands in the very
            # next block instead (see e.g. protocol 9's layout).
            for line in lines:
                if line.lower() not in _PROTOCOL_HEADER_LINE and not line.isdigit():
                    return line
            return None
    return None


def _extract_protocol_page(page) -> Optional[Dict]:
    width = page.rect.width
    panel_x = width * _PANEL_X_FRACTION
    blocks = [b for b in page.get_text("blocks") if b[6] == 0 and b[1] < 780]  # exclude page-number footer

    if not any(_has_protocol_header_line(b[4]) for b in blocks):
        return None

    title = _page_protocol_title(blocks)
    if not title:
        # Title sometimes sits in its own block right after the header block
        # rather than sharing one with it (protocol 9) — fall back to the
        # next non-header, non-numeric, reasonably short block near the top.
        for b in sorted(blocks, key=lambda b: b[1]):
            t = _clean_text(b[4])
            if t and not _has_protocol_header_line(t) and not t.isdigit() and len(t) < 120:
                title = t
                break
    if not title:
        return None

    table_start_y = None
    for b in blocks:
        if _DRUGS_AND_DOSES_RE.search(b[4]):
            table_start_y = b[1]
            break

    step_blocks = []
    panel_blocks = []
    table_blocks = []
    footnote_blocks = []

    for b in blocks:
        text = _clean_text(b[4])
        if not text or _has_protocol_header_line(text) or text == title:
            continue

        if table_start_y is not None and b[1] >= table_start_y:
            table_blocks.append(b)
            continue

        if _FOOTNOTE_START_RE.match(text):
            footnote_blocks.append(b)
            continue

        if b[0] >= panel_x:
            panel_blocks.append(b)
        else:
            step_blocks.append(b)

    # page.get_text("blocks") is NOT in visual reading order (same issue as
    # the AWaRe infographics) — each zone must be sorted top-to-bottom by
    # y-position itself, otherwise "step 1"/"step 2"/... and their actions
    # come out interleaved in the wrong order, which is exactly what "don't
    # split a step from its dose" is trying to prevent.
    step_lines = [_clean_text(b[4]) for b in sorted(step_blocks, key=lambda b: b[1])]
    panel_lines = [_clean_text(b[4]) for b in sorted(panel_blocks, key=lambda b: b[1])]
    footnote_lines = [_clean_text(b[4]) for b in sorted(footnote_blocks, key=lambda b: b[1])]

    # Reconstruct the dose table by reading remaining blocks top-to-bottom,
    # left-to-right within each row band — not a strict grid parse, but it
    # keeps each medication adjacent to its own starting/intensification
    # dose, which is what actually matters for not separating a drug from
    # its dose.
    table_lines = [_clean_text(b[4]) for b in sorted(table_blocks, key=lambda b: (round(b[1] / 6), b[0]))]
    table_lines = [t for t in table_lines if t]

    return {
        "title": title,
        "step_text": " ".join(step_lines),
        "panel_text": " ".join(panel_lines),
        "table_text": " ".join(table_lines),
        "footnote_text": " ".join(footnote_lines),
    }


def _extract_box_page(blocks) -> Optional[Dict]:
    for b in blocks:
        first_line = b[4].split("\n")[0].strip()
        match = _BOX_HEADER_RE.match(_clean_text(first_line))
        if match:
            all_text = " ".join(_clean_text(x[4]) for x in blocks if x[1] < 780)
            return {"title": _clean_text(first_line), "text": all_text}
    return None


def parse_and_chunk_hearts_pdf(file_path: str) -> List[Dict]:
    doc = fitz.open(file_path)

    prose_pages: List[Dict] = []
    protocol_groups: List[Dict] = []  # [{"title", "page_number", "sections": [...]}]
    pending_box: Optional[Dict] = None

    for page_index in range(len(doc)):
        page = doc[page_index]
        page_number = page_index + 1
        blocks = [b for b in page.get_text("blocks") if b[6] == 0]

        protocol = _extract_protocol_page(page)
        if protocol is not None:
            sections = []
            if pending_box is not None:
                sections.append({
                    "title": f"{protocol['title']} — {pending_box['title']}",
                    "page_number": page_number - 1,
                    "text": f"[{protocol['title']} — {pending_box['title']}]\n{pending_box['text']}",
                })
                pending_box = None

            if protocol["step_text"] or protocol["table_text"]:
                combined = f"[{protocol['title']} — Steps and Drug Doses]\n"
                combined += protocol["step_text"]
                if protocol["table_text"]:
                    combined += f"\nDrugs and doses: {protocol['table_text']}"
                if protocol["footnote_text"]:
                    combined += f"\nNotes: {protocol['footnote_text']}"
                sections.append({
                    "title": f"{protocol['title']} — Steps and Drug Doses",
                    "page_number": page_number,
                    "text": combined,
                })

            if protocol["panel_text"]:
                sections.append({
                    "title": f"{protocol['title']} — Provision for Specific Patients / Lifestyle Advice",
                    "page_number": page_number,
                    "text": f"[{protocol['title']} — Provision for Specific Patients / Lifestyle Advice]\n{protocol['panel_text']}",
                })

            protocol_groups.append({"title": protocol["title"], "page_number": page_number, "sections": sections})
            continue

        box = _extract_box_page(blocks)
        if box is not None:
            pending_box = {"title": box["title"], "text": box["text"]}
            continue

        prose_pages.append({"page_number": page_number, "text": page.get_text("text")})

    doc.close()

    all_chunks: List[Dict] = []
    chunk_counter = 0

    # Front-matter / narrative pages: same generic strategy as the Polypharmacy guide.
    cleaned_prose = strip_boilerplate(prose_pages)
    prose_sections = split_into_sections(cleaned_prose)
    for chunk in pack_sections_into_chunks(prose_sections):
        chunk_counter += 1
        chunk_dict = {
            "chunk_id": f"hearts_chunk_{chunk_counter}",
            "text": chunk["text"],
            "page_number": chunk["page_number"],
            "section_title": chunk["section_title"],
            "category": "General",
        }
        # Pages 1-13 are cover/overview/TOC-style front matter (e.g. the
        # protocol list on page 12 repeats "first-line treatment" for all 9
        # protocol names) — lexically dense enough to outrank actual protocol
        # content for generic queries. Flagged so the retriever can exclude
        # it on request; left unset (not False) for real content, so a
        # simple "$ne: True" filter naturally includes documents that never
        # set this key at all (verified against a live Chroma collection).
        if chunk["page_number"] <= 13:
            chunk_dict["is_front_matter"] = True
        all_chunks.append(chunk_dict)

    # Each protocol is packed on its own (never merged with a different
    # protocol), keeping the step sequence + dose table together as one
    # chunk whenever it fits the token budget; the side panel only becomes
    # its own chunk when the combined size doesn't fit — exactly what
    # pack_sections_into_chunks already guarantees by never splitting a
    # section internally.
    for group in protocol_groups:
        is_diabetes = "diabetes" in group["title"].lower()
        for chunk in pack_sections_into_chunks(group["sections"]):
            chunk_counter += 1
            all_chunks.append({
                "chunk_id": f"hearts_chunk_{chunk_counter}",
                "text": chunk["text"],
                "page_number": chunk["page_number"],
                "section_title": chunk["section_title"],
                "topic_name": group["title"],
                "disease_name": "Diabetes" if is_diabetes else "Hypertension",
                "category": "Diabetes Protocol" if is_diabetes else "Hypertension Protocol",
            })

    return all_chunks
