import json
from typing import List, Dict
from fastapi import HTTPException
from app.rag.llm_provider import generate_content


def _safe_generate_json(prompt: str) -> dict:
    """
    Calls the LLM and parses its response as JSON, stripping markdown
    code fences if present.
    """
    try:
        result = generate_content(prompt)
    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=f"All AI providers are currently unavailable. Please try again later. ({str(e)})"
        )

    text = result["text"].strip()

    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"score": None, "reasoning": "Failed to parse evaluation output", "raw_text": text}


def evaluate_faithfulness(answer: str, chunks: List[Dict]) -> Dict:
    """
    Measures whether every claim in the answer is actually supported by
    the retrieved source chunks (i.e., the answer doesn't hallucinate
    beyond what the sources say). Score from 0.0 (not faithful) to 1.0
    (fully faithful).
    """
    context_text = "\n\n".join(f"[Page {c['page_number']}] {c['text']}" for c in chunks)

    prompt = f"""Evaluate whether the following answer is fully supported by the given sources, with no unsupported or hallucinated claims.

Sources:
{context_text}

Answer:
{answer}

Return ONLY a valid JSON object (no markdown, no explanation outside the JSON) with this structure:
{{"score": <float between 0.0 and 1.0>, "reasoning": "<brief one-sentence justification>"}}

A score of 1.0 means every claim is directly supported. A score of 0.0 means the answer is unsupported or contradicts the sources.

JSON output:"""

    return _safe_generate_json(prompt)


def evaluate_answer_relevancy(question: str, answer: str) -> Dict:
    """
    Measures whether the answer actually addresses what was asked,
    rather than being generic, off-topic, or incomplete. Score from
    0.0 (irrelevant) to 1.0 (fully relevant and on-point).
    """
    prompt = f"""Evaluate how relevant and on-point the following answer is to the question asked.

Question:
{question}

Answer:
{answer}

Return ONLY a valid JSON object (no markdown, no explanation outside the JSON) with this structure:
{{"score": <float between 0.0 and 1.0>, "reasoning": "<brief one-sentence justification>"}}

A score of 1.0 means the answer directly and completely addresses the question. A score of 0.0 means it's off-topic or doesn't address it at all.

JSON output:"""

    return _safe_generate_json(prompt)


def evaluate_context_relevancy(question: str, chunks: List[Dict]) -> Dict:
    """
    Measures whether the retrieved chunks were actually relevant to the
    question, independent of how the answer was generated. This isolates
    retrieval quality from generation quality. Score from 0.0 to 1.0.
    """
    if not chunks:
        return {"score": 0.0, "reasoning": "No chunks were retrieved."}

    context_text = "\n\n".join(f"[Page {c['page_number']}] {c['text']}" for c in chunks)

    prompt = f"""Evaluate how relevant the following retrieved document excerpts are to the question, regardless of how any answer was phrased.

Question:
{question}

Retrieved excerpts:
{context_text}

Return ONLY a valid JSON object (no markdown, no explanation outside the JSON) with this structure:
{{"score": <float between 0.0 and 1.0>, "reasoning": "<brief one-sentence justification>"}}

A score of 1.0 means the excerpts are highly relevant and sufficient to answer the question. A score of 0.0 means they are irrelevant.

JSON output:"""

    return _safe_generate_json(prompt)


def evaluate_answer(question: str, answer: str, chunks: List[Dict]) -> Dict:
    """
    Runs all three evaluation metrics for a single question/answer pair
    and returns a combined report.
    """
    faithfulness = evaluate_faithfulness(answer, chunks)
    answer_relevancy = evaluate_answer_relevancy(question, answer)
    context_relevancy = evaluate_context_relevancy(question, chunks)

    return {
        "faithfulness": faithfulness,
        "answer_relevancy": answer_relevancy,
        "context_relevancy": context_relevancy
    }