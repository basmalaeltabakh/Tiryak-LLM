import re
from typing import Dict, List, Optional

# Citations are instructed as "[Document Name, Page X]" or
# "[Document Name, Section: Y, Page X]" (generator.py's build_context_prompt),
# but models tend to instead echo the field order of the source labels shown
# in context ("Document: X, Page N, Topic: ..., Section: Y") rather than the
# instructed order — observed directly: real generated citations came back as
# "[Document: X, Page 14, Section: Y]", Page before Section, with a
# "Document: " prefix, none of which the stricter order-dependent pattern
# matched. So: find each bracketed group, then independently pull the page
# number (wherever it sits) and the leading document-name fragment (before
# the first comma), instead of anchoring to one exact field order.
_BRACKET_PATTERN = re.compile(r"\[([^\[\]]+)\]")
_PAGE_PATTERN = re.compile(r"Page\s+(\d+)", re.IGNORECASE)
_DOCUMENT_PREFIX_PATTERN = re.compile(r"^Document:\s*", re.IGNORECASE)


def extract_citations(answer: str) -> List[Dict]:
    """
    Parses inline citations out of generated answer text — any bracketed
    group containing "Page N" is treated as a citation.
    Returns a list of {"raw": str, "document_fragment": str, "page_number": int}.
    """
    citations = []
    for bracket_match in _BRACKET_PATTERN.finditer(answer):
        content = bracket_match.group(1)
        page_match = _PAGE_PATTERN.search(content)
        if not page_match:
            continue  # not a citation — some other bracketed text

        doc_fragment = content.split(",")[0].strip()
        doc_fragment = _DOCUMENT_PREFIX_PATTERN.sub("", doc_fragment).strip()

        citations.append({
            "raw": bracket_match.group(0),
            "document_fragment": doc_fragment,
            "page_number": int(page_match.group(1)),
        })
    return citations


def validate_citations(answer: str, chunks: List[Dict]) -> Dict:
    """
    Cross-checks every inline citation the model wrote against the chunks
    actually retrieved and used for this answer — deterministic, no LLM call.

    A citation is VALID if its page number matches a retrieved chunk's
    page_number, AND its leading text overlaps (case-insensitive substring
    either direction) with EITHER that chunk's filename OR its section_title.
    The prompt instructs citing the document name, but small/fast models
    (observed with the Groq fallback) sometimes cite the section title
    instead — still a real, non-hallucinated pointer to the actual retrieved
    chunk, just not the instructed style, so it's counted as valid rather
    than as a fabrication. A citation naming neither — wrong document, wrong
    section, or a page never retrieved — is what this is actually meant to
    catch.

    Returns:
    {
        "citations": [{"raw", "document_fragment", "page_number", "valid"}],
        "citation_accuracy": float | None,  # valid / total, None if no citations found
        "num_citations": int,
        "num_valid": int,
        "invalid_citations": [...],  # the raw strings that didn't match any retrieved chunk
    }
    """
    citations = extract_citations(answer)

    chunks_by_page = {}
    for c in chunks:
        chunks_by_page.setdefault(c["page_number"], []).append(c)

    invalid = []
    for citation in citations:
        candidates = chunks_by_page.get(citation["page_number"], [])
        frag_low = citation["document_fragment"].lower()

        def _overlaps(field_value: Optional[str]) -> bool:
            if not field_value:
                return False
            field_low = field_value.lower()
            return frag_low in field_low or field_low in frag_low

        is_valid = any(
            _overlaps(c["filename"]) or _overlaps(c.get("section_title"))
            for c in candidates
        )
        citation["valid"] = is_valid
        if not is_valid:
            invalid.append(citation["raw"])

    num_valid = sum(1 for c in citations if c["valid"])
    accuracy = round(num_valid / len(citations), 3) if citations else None

    return {
        "citations": citations,
        "citation_accuracy": accuracy,
        "num_citations": len(citations),
        "num_valid": num_valid,
        "invalid_citations": invalid,
    }
