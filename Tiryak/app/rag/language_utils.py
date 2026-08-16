def detect_language(text: str) -> str:
    """
    Simple heuristic: returns "ar" if the text contains Arabic-range
    characters, otherwise "en". Used to pick response language/dialect.
    """
    if not text:
        return "en"
    return "ar" if any("\u0600" <= ch <= "\u06FF" for ch in text) else "en"