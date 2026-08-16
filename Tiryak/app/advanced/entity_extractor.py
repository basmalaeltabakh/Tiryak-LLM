import json
from typing import List, Dict
from fastapi import HTTPException
from app.rag.llm_provider import generate_content


def _safe_generate_json(prompt: str) -> dict:
    """
    Calls the LLM and parses its response as JSON, stripping markdown
    code fences if present (some models wrap JSON in ```json ... ```).
    """
    try:
        result = generate_content(prompt)
    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=f"All AI providers are currently unavailable. Please try again later. ({str(e)})"
        )

    text = result["text"].strip()

    # Strip markdown code fences if the model added them despite instructions
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Return the raw text as a fallback so the caller can still see something
        return {"error": "Failed to parse structured output", "raw_text": text}


def extract_entities(chunks: List[Dict]) -> Dict:
    """
    Extracts named entities (people, organizations, dates, monetary amounts,
    percentages) from the document's chunks, aggregated across the whole document.
    """
    combined_text = "\n\n".join(
        f"[Page {c['page_number']}] {c['text']}" for c in chunks
    )

    prompt = f"""Extract all named entities from the following document text. Return ONLY a valid JSON object (no markdown formatting, no explanation) with this exact structure:

{{
  "people": ["name1", "name2"],
  "organizations": ["org1", "org2"],
  "dates": ["date1", "date2"],
  "monetary_amounts": ["amount1", "amount2"],
  "percentages": ["percentage1", "percentage2"]
}}

Only include entities that actually appear in the text. Do not invent or infer entities that aren't explicitly mentioned. Keep entities in their original language (Arabic or English) as they appear in the text.

Document text:
{combined_text}

JSON output:"""

    return _safe_generate_json(prompt)


def extract_tables(chunks: List[Dict]) -> Dict:
    """
    Detects and extracts tabular data from the document's chunks.
    Returns a list of tables, each with headers and rows.
    """
    combined_text = "\n\n".join(
        f"[Page {c['page_number']}] {c['text']}" for c in chunks
    )

    prompt = f"""Look for any tabular data (structured data with clear rows and columns, such as pricing tables, schedules, or comparison data) in the following document text. Return ONLY a valid JSON object (no markdown formatting, no explanation) with this exact structure:

{{
  "tables": [
    {{
      "title": "short descriptive title for this table",
      "page_number": <int>,
      "headers": ["column1", "column2"],
      "rows": [
        ["value1", "value2"],
        ["value3", "value4"]
      ]
    }}
  ]
}}

If no tabular data is found, return {{"tables": []}}. Do not invent tables that aren't present in the text.

Document text:
{combined_text}

JSON output:"""

    return _safe_generate_json(prompt)