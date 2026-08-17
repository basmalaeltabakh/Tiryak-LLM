"""
Section-aware parser for the WHO AWaRe Antibiotic Book (Web Annex: Infographics).

Why this document needs its own parser instead of the generic parse_document()
+ chunk_document() path (see app/ingestion/parsers.py, app/ingestion/chunker.py):

This PDF is a graphic, two-column "infographic" layout (Definition / Diagnosis /
Most Likely Pathogens / Treatment blocks placed side by side), not linear prose.
PyMuPDF's plain get_text("text") — what the generic parser uses — reads blocks in
internal object order, which does NOT match the visual reading order for this
layout: Treatment text comes out before Diagnosis, and Definition ends up last.
Grouping that scrambled text with the generic word-count chunker produces a single
per-page chunk that mixes unrelated sections together.

This module instead reads each page as positioned blocks (bounding boxes), splits
them into a left/right column by x-position, sorts each column top-to-bottom by
y-position, and walks the result looking for the WHO AWaRe template's known
section headers (Definition, Diagnosis, Antibiotic Treatment, etc.) to split the
page into one chunk per section. Verified against all 160 pages of the source PDF:
149 pages recognized as disease/drug infographics (11 are cover/TOC/copyright/
divider pages, correctly skipped), covering all 23 Primary Health Care conditions,
all 18 Hospital Facility conditions, and all 7 Reserve Antibiotics monographs.
"""

import re
from typing import Dict, List, Optional

import fitz

from app.ingestion.chunker import pack_sections_into_chunks

CATEGORY_LABELS = {
    "primary health care": "Primary Health Care",
    "hospital facility": "Hospital Facility",
    "reserve antibiotics": "Reserve Antibiotics",
}

# Known section header text (lowercased) -> (canonical display label, parent section or None).
# Covers every header observed 5+ times across the document. Anything else falls
# back to an "Overview" bucket rather than being silently dropped or attached to
# the wrong section (e.g. the Centor Clinical Scoring System table in Pharyngitis,
# which doesn't follow the standard template).
SECTION_DEFS = {
    "definition": ("Definition", None),
    "most likely pathogens": ("Most Likely Pathogens", None),
    "diagnosis": ("Diagnosis", None),
    "clinical presentation": ("Clinical Presentation", "Diagnosis"),
    "microbiology tests": ("Microbiology Tests", "Diagnosis"),
    "other laboratory tests": ("Other Laboratory Tests", "Diagnosis"),
    "imaging": ("Imaging", "Diagnosis"),
    "treatment": ("Treatment", None),
    "no antibiotic care": ("No Antibiotic Care", "Treatment"),
    "symptomatic treatment": ("Symptomatic Treatment", "Treatment"),
    "symptomatictreatment": ("Symptomatic Treatment", "Treatment"),  # PDF drops the space here
    "topical treatment": ("Topical Treatment", "Treatment"),
    "prophylactic antibiotics": ("Prophylactic Antibiotics", "Treatment"),
    "prevention": ("Prevention", "Treatment"),
    "antibiotic treatment": ("Antibiotic Treatment", "Treatment"),
    "antibiotic treatment duration": ("Antibiotic Treatment Duration", "Treatment"),
    "clinical considerations": ("Clinical Considerations", "Treatment"),
    "first choice": ("First Choice", "Antibiotic Treatment"),
    "second choice": ("Second Choice", "Antibiotic Treatment"),
    "mild cases": ("Mild Cases", "Antibiotic Treatment"),
    "severe cases": ("Severe Cases", "Antibiotic Treatment"),
    "mild to moderate cases": ("Mild to Moderate Cases", "Antibiotic Treatment"),
    "uncomplicated": ("Uncomplicated", "Antibiotic Treatment"),
    "complicated": ("Complicated", "Antibiotic Treatment"),
    # Reserve-drug monograph template (different vocabulary from the disease template)
    "pharmacology": ("Pharmacology", None),
    "indications for use": ("Indications for Use", None),
    "empiric use": ("Empiric Use", "Indications for Use"),
    "targeted treatment": ("Targeted Treatment", "Indications for Use"),
    "targetedtreatment": ("Targeted Treatment", "Indications for Use"),  # PDF drops the space here
    "important considerations": ("Important Considerations", None),
    "formulations": ("Formulations", None),
    "spectrum of activity": ("Spectrum of Activity", None),
    "toxicity": ("Toxicity", None),
    "dose": ("Dose", None),
    "adults": ("Adults", "Dose"),
    "children": ("Children", "Dose"),
    "children or neonates": ("Children or Neonates", "Dose"),
}

# The source PDF's subset font drops the "fi"/"fl" ligatures for a few words
# (e.g. "Definition" extracts as "De<U+001F>nition"), rendering them as raw
# control characters. \x1f and \x93 are also reused as bullet-point icon glyphs
# elsewhere, so they're only restored to "fi"/"fl" when they sit strictly
# between two letters (a real word); everywhere else they're stripped as noise.
_MIDWORD_FI_RE = re.compile(r"(?<=[A-Za-z])\x1f(?=[A-Za-z])")
_MIDWORD_FL_RE = re.compile(r"(?<=[A-Za-z])\x93(?=[A-Za-z])")
_ICON_GLYPHS_RE = re.compile(r"[-]")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_PAGE_OF_RE = re.compile(r"^page\s+\d+\s+of\s+\d+$", re.IGNORECASE)

# Running footer text (book title / "Web Annex..." / page number strip) sits
# below this y-coordinate on every page — excluded before column splitting.
_FOOTER_Y_THRESHOLD = 550


def _clean_text(text: str) -> str:
    text = _MIDWORD_FI_RE.sub("fi", text)
    text = _MIDWORD_FL_RE.sub("fl", text)
    text = _ICON_GLYPHS_RE.sub("", text)
    text = _CONTROL_CHARS_RE.sub("", text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _detect_category(text: str) -> Optional[str]:
    return CATEGORY_LABELS.get(_clean_text(text).strip().lower())


def _match_header(line: str):
    return SECTION_DEFS.get(line.lower().rstrip(":"))


def _process_column(blocks: List, current: Optional[Dict], deferred: List[str], sections: List[Dict]):
    """
    Walks one column's blocks top-to-bottom, splitting into sections at each
    recognized header. `current` is the section carried in from the caller (or
    None); `deferred` holds header names whose body text lives in the OTHER
    column — this happens when two header labels are printed together in one
    physical text frame (e.g. "Definition" and "Most Likely Pathogens" share a
    block, but only Definition's body follows in this column; Most Likely
    Pathogens' body is the first thing in the other column).
    """
    for block in blocks:
        raw_text = _clean_text(block[4])
        if not raw_text:
            continue
        lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
        header_matches = [(l, _match_header(l)) for l in lines]
        is_pure_header_cluster = len(lines) >= 2 and all(m is not None for _, m in header_matches)

        if is_pure_header_cluster:
            first_line, first_match = header_matches[0]
            if current is not None and current["words"]:
                sections.append(current)
            label, parent = first_match
            current = {"section": f"{parent} - {label}" if parent else label, "words": []}
            for _, m in header_matches[1:]:
                label, parent = m
                deferred.append(f"{parent} - {label}" if parent else label)
            continue

        for line in lines:
            match = _match_header(line)
            if match:
                if current is not None and current["words"]:
                    sections.append(current)
                label, parent = match
                current = {"section": f"{parent} - {label}" if parent else label, "words": []}
            else:
                if current is None:
                    current = {"section": deferred.pop(0), "words": []} if deferred else {"section": "Overview", "words": []}
                current["words"].append(line)

    return current, deferred


def _extract_page_sections(page) -> Optional[Dict]:
    """
    Reconstructs one AWaRe infographic page into {category, title, sections}.
    Returns None for pages that aren't a recognizable disease/drug infographic
    (cover, copyright, table of contents, section dividers) so they're skipped
    rather than ingested as noise.
    """
    width = page.rect.width
    mid_x = width / 2

    raw_blocks = [b for b in page.get_text("blocks") if b[6] == 0]
    blocks = [b for b in raw_blocks if b[1] < _FOOTER_Y_THRESHOLD]

    # The running category header sits in the outer margin, which mirrors
    # left/right on facing book pages — it can land in either column depending
    # on whether the page number is odd or even. Find it wherever it is rather
    # than assuming a side, then exclude it before splitting into columns.
    category = None
    category_idx = None
    for idx, b in enumerate(blocks):
        cat = _detect_category(b[4])
        if cat:
            category, category_idx = cat, idx
            break
    if category is None:
        return None
    blocks = [b for i, b in enumerate(blocks) if i != category_idx]

    left = sorted([b for b in blocks if b[0] < mid_x], key=lambda b: b[1])
    right = sorted([b for b in blocks if b[0] >= mid_x], key=lambda b: b[1])
    if not left:
        return None

    title = _clean_text(left[0][4].split("\n")[0])
    if not title:
        return None
    left = left[1:]
    if left and _PAGE_OF_RE.match(_clean_text(left[0][4])):
        left = left[1:]  # drop "Page X of Y" marker for multi-page conditions

    sections: List[Dict] = []
    deferred: List[str] = []

    current, deferred = _process_column(left, None, deferred, sections)
    if current is not None and current["words"]:
        sections.append(current)

    # A header deferred from the left column becomes the right column's
    # starting bucket instead of None, so its body (printed in the other
    # column) attaches to the right section instead of falling into "Overview".
    current = {"section": deferred.pop(0), "words": []} if deferred else None
    current, deferred = _process_column(right, current, deferred, sections)
    if current is not None and current["words"]:
        sections.append(current)

    return {"category": category, "title": title, "sections": sections}


def parse_and_chunk_aware_pdf(file_path: str) -> List[Dict]:
    """
    Parses and chunks the WHO AWaRe infographic PDF in one pass.

    Each page's sections (Definition, Diagnosis, Antibiotic Treatment, etc.)
    are packed into as few chunks as possible within the shared token budget
    (pack_sections_into_chunks — the same packer the Polypharmacy chunker
    uses) so a whole infection section/drug monograph becomes one chunk when
    it fits, rather than fragmenting into one chunk per subsection. A section
    is never split internally by packing — the recommendation, its dose, and
    its duration all live inside one section's text (produced by
    _extract_page_sections), so packing can only ever combine or separate
    whole sections, never cut one apart.

    Packing is scoped to a single page, not merged across pages that happen
    to share a title (e.g. Bronchitis has separate adult and pediatric
    pages) — the book doesn't label which page is which population as
    extractable text, so combining them would risk blending two different
    dosing regimens into one ambiguous chunk. Page-level scoping keeps each
    population's dosing in its own chunk, distinguishable by page_number.

    Produces chunks shaped like the generic chunker's output (chunk_id, text,
    page_number, section_title) plus AWaRe-specific metadata keys
    (topic_name, disease_name, category) that add_chunks_to_store() picks up
    automatically.
    """
    doc = fitz.open(file_path)
    all_chunks: List[Dict] = []
    chunk_counter = 0

    for page_index in range(len(doc)):
        page = doc[page_index]
        page_number = page_index + 1
        extracted = _extract_page_sections(page)
        if extracted is None:
            continue

        category = extracted["category"]
        title = extracted["title"]
        is_drug_monograph = category == "Reserve Antibiotics"

        page_sections = [
            {
                "title": f"{title} — {section['section']}",
                "page_number": page_number,
                "text": f"[{title} — {section['section']}]\n{' '.join(section['words'])}",
            }
            for section in extracted["sections"]
            if section["words"]
        ]

        for chunk in pack_sections_into_chunks(page_sections):
            chunk_counter += 1
            all_chunks.append({
                "chunk_id": f"aware_chunk_{chunk_counter}",
                "text": chunk["text"],
                "page_number": chunk["page_number"],
                "section_title": chunk["section_title"],
                "topic_name": title,
                "disease_name": None if is_drug_monograph else title,
                "category": category,
            })

    doc.close()
    return all_chunks
