import base64
import json
from typing import Dict, List
from fastapi import HTTPException
import google.generativeai as genai
from app.config import GEMINI_API_KEY, GEMINI_MODEL_NAME

genai.configure(api_key=GEMINI_API_KEY)


def extract_medication_names_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> Dict:
    """
    Reads a photo of a prescription or medication box/label and extracts
    only the medication name(s) as plain text. Does NOT interpret dosage,
    make clinical judgments, or guess at unclear handwriting — if the text
    isn't clearly legible, it says so explicitly rather than guessing,
    since a wrong guess here is far more dangerous than admitting uncertainty.
    """
    model = genai.GenerativeModel(GEMINI_MODEL_NAME)

    prompt = """You are reading a photo of either a medication box/label or a handwritten prescription.

Your ONLY task is to extract the medication name(s) that are CLEARLY and UNAMBIGUOUSLY legible in the image. Follow these rules strictly:

1. Do NOT guess at unclear handwriting. If a medication name is not clearly legible, do not include it — flag it instead as unclear.
2. Do NOT interpret dosage, frequency, or any clinical instructions. Extract names only.
3. Do NOT make any clinical judgment about the medication.
4. If the image contains no readable medication name at all, say so.

Return ONLY a valid JSON object (no markdown, no explanation outside the JSON) with this structure:
{
  "clearly_read_names": ["name1", "name2"],
  "unclear_count": <number of medication entries that appear present but are not clearly legible>,
  "notes": "<one short sentence, e.g. 'handwriting for the 2nd item is illegible'>"
}

JSON output:"""

    image_part = {"mime_type": mime_type, "data": image_bytes}

    try:
        response = model.generate_content([prompt, image_part])
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Image reading failed: {str(e)}")

    text = response.text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"clearly_read_names": [], "unclear_count": 0, "notes": "Could not parse image analysis."}