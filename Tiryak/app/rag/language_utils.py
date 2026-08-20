from typing import Optional
from app.rag.llm_provider import generate_content


def detect_language(text: str) -> str:
    """
    Simple heuristic: returns "ar" if the text contains Arabic-range
    characters, otherwise "en". Used to pick response language/dialect.
    """
    if not text:
        return "en"
    return "ar" if any("\u0600" <= ch <= "\u06FF" for ch in text) else "en"


def translate_query_to_english(text: str) -> Optional[str]:
    """
    Translates an Arabic clinical question into English for retrieval
    embedding. The corpus is entirely English-source text, so an Arabic
    query is always a cross-lingual match against it, and this embedding
    model (multilingual-e5-base) scores that systematically worse than a
    same-language English query for identical correct content \u2014 measured
    directly: Arabic queries land ~0.06-0.10 higher cosine distance than
    their English equivalent for the same correct source page, and for
    several real queries the correct page fell out of the top-25 results
    entirely. Translating first turns retrieval into an English-to-English
    match, sidestepping that gap instead of just tolerating it with a
    looser distance threshold.

    Returns None if translation fails (e.g. all LLM providers unavailable)
    so the caller can fall back to embedding the original Arabic text.
    """
    prompt = f"""Translate the following clinical/medical question from Arabic to English.
Keep drug names, medical terms, and any text already in English or Latin script unchanged.
Output ONLY the English translation, nothing else \u2014 no quotes, no explanation.

Arabic text: {text}

English translation:"""

    try:
        result = generate_content(prompt)
    except RuntimeError:
        return None

    translated = result["text"].strip().strip('"').strip()
    return translated or None