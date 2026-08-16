from typing import Optional
import google.generativeai as genai
import google.api_core.exceptions as google_exceptions
from groq import Groq
import re

from app.config import GEMINI_API_KEY, GEMINI_MODEL_NAME, GROQ_API_KEY, GROQ_MODEL_NAME

genai.configure(api_key=GEMINI_API_KEY)

_gemini_model = None
_groq_client = None


def _get_gemini_model():
    global _gemini_model
    if _gemini_model is None:
        _gemini_model = genai.GenerativeModel(GEMINI_MODEL_NAME)
    return _gemini_model


def _get_groq_client():
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=GROQ_API_KEY)
    return _groq_client


def _call_gemini(prompt: str) -> str:
    model = _get_gemini_model()
    response = model.generate_content(prompt)
    return response.text.strip()


def _call_groq(prompt: str) -> str:
    client = _get_groq_client()
    response = client.chat.completions.create(
        model=GROQ_MODEL_NAME,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()

def _clean_generated_text(text: str) -> str:
    """
    Strips stray CJK (Chinese/Japanese/Korean) characters that can leak
    into Arabic/English output from multilingual models (a known issue
    with some LLMs, especially smaller/quantized ones, when generating
    lower-resource languages like Arabic).
    """
    cjk_pattern = re.compile(
        r'[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]+'
    )
    cleaned = cjk_pattern.sub('', text)
    # Clean up any double spaces left behind after removal
    cleaned = re.sub(r'\s{2,}', ' ', cleaned)
    return cleaned.strip()
def generate_content(prompt: str, preferred_provider: Optional[str] = None) -> dict:
    """
    Generates text using an LLM, with automatic fallback between providers.

    preferred_provider: "gemini", "groq", or None (auto: try gemini first, fallback to groq)

    Returns: {"text": str, "provider_used": str}
    """
    if preferred_provider == "gemini":
        providers_to_try = ["gemini"]
    elif preferred_provider == "groq":
        providers_to_try = ["groq"]
    else:
        providers_to_try = ["gemini", "groq"]

    last_error = None

    for provider in providers_to_try:
        try:
            if provider == "gemini":
                text = _call_gemini(prompt)
            else:
                text = _call_groq(prompt)

            text = _clean_generated_text(text)
            return {"text": text, "provider_used": provider}

        except google_exceptions.ResourceExhausted as e:
            last_error = e
            continue
        except Exception as e:
            last_error = e
            continue

    raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")