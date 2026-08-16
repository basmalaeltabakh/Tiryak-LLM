import io
import uuid
from pathlib import Path
from fastapi import HTTPException
from groq import Groq
from gtts import gTTS

from app.config import GROQ_API_KEY, UPLOADS_DIR

_groq_client = None

WHISPER_MODEL_NAME = "whisper-large-v3"


def _get_groq_client():
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=GROQ_API_KEY)
    return _groq_client


def transcribe_audio(audio_bytes: bytes, filename: str = "audio.wav") -> str:
    """
    Transcribes speech from audio bytes into text using Groq's hosted
    Whisper model. Supports both Arabic and English (Whisper auto-detects
    the language).
    """
    client = _get_groq_client()

    try:
        response = client.audio.transcriptions.create(
            file=(filename, audio_bytes),
            model=WHISPER_MODEL_NAME,
        )
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Speech-to-text service is currently unavailable. ({str(e)})"
        )

    return response.text.strip()


def text_to_speech(text: str, language: str = "auto") -> str:
    """
    Converts text into speech audio, saved as an MP3 file.
    Returns the path to the generated audio file.

    language: "ar" for Arabic, "en" for English, or "auto" to detect
              based on the presence of Arabic characters in the text.
    """
    if language == "auto":
        has_arabic = any("\u0600" <= ch <= "\u06FF" for ch in text)
        language = "ar" if has_arabic else "en"

    try:
        tts = gTTS(text=text, lang=language)
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Text-to-speech generation failed. ({str(e)})"
        )

    output_filename = f"tts_{uuid.uuid4()}.mp3"
    output_path = UPLOADS_DIR / output_filename
    tts.save(str(output_path))

    return str(output_path)