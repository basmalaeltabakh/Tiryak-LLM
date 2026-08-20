import json
from typing import List, Dict
from fastapi import HTTPException
from app.rag.llm_provider import generate_content
from app.config import CHUNK_RELEVANCE_DISTANCE_THRESHOLD


def compute_retrieval_confidence(
    chunks: List[Dict], distance_threshold: float = CHUNK_RELEVANCE_DISTANCE_THRESHOLD
) -> str:
    """
    Estimates confidence based on how close the retrieved chunks are
    to the query (cosine distance). Lower distance = higher confidence.
    Returns one of: "high", "medium", "low".
    """
    if not chunks:
        return "low"

    avg_distance = sum(c["distance"] for c in chunks) / len(chunks)

    if avg_distance < distance_threshold * 0.7:
        return "high"
    elif avg_distance < distance_threshold:
        return "medium"
    else:
        return "low"


def verify_answer_grounding(answer: str, chunks: List[Dict]) -> Dict:
    """
    Claim-level grounding check: asks the LLM to identify which specific
    sentences/claims in the answer (if any) are NOT supported by the source
    chunks, rather than only a single whole-answer verdict. A whole-answer
    "partially_grounded" label is not actionable on its own — this makes it
    possible to actually flag or act on the specific unsupported part
    (see app/rag/pipeline.py, which appends a caveat naming the unsupported
    claim rather than just displaying an opaque verdict).

    Returns {"verdict": "grounded"|"partially_grounded"|"not_grounded",
             "unsupported_claims": [str, ...]}  (empty list when fully grounded)
    """
    context_text = "\n\n".join(
        f"[Page {c['page_number']}]\n{c['text']}" for c in chunks
    )

    verification_prompt = f"""You are verifying whether an answer is factually supported by the given sources, claim by claim.

Sources:
{context_text}

Answer to verify:
{answer}

Identify any specific sentence or claim in the answer that is NOT directly supported by the sources above (ignore boilerplate like safety disclaimers). Return ONLY a valid JSON object (no markdown, no explanation outside the JSON):
{{"unsupported_claims": ["<exact unsupported sentence or claim>", ...], "verdict": "grounded" | "partially_grounded" | "not_grounded"}}

If every claim is supported, return an empty list and "grounded".

JSON output:"""

    try:
        result = generate_content(verification_prompt)
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
        parsed = json.loads(text)
        verdict = parsed.get("verdict", "partially_grounded")
        if verdict not in ("grounded", "partially_grounded", "not_grounded"):
            verdict = "partially_grounded"
        unsupported = parsed.get("unsupported_claims") or []
        return {"verdict": verdict, "unsupported_claims": unsupported}
    except json.JSONDecodeError:
        # Fall back to a coarse keyword read of the raw text rather than
        # failing the whole request over a formatting slip.
        low = text.lower()
        if "not_grounded" in low:
            verdict = "not_grounded"
        elif "partially_grounded" in low:
            verdict = "partially_grounded"
        elif "grounded" in low:
            verdict = "grounded"
        else:
            verdict = "partially_grounded"
        return {"verdict": verdict, "unsupported_claims": []}


def get_confidence_report(
    answer: str,
    chunks: List[Dict],
    check_grounding: bool = True,
    distance_threshold: float = CHUNK_RELEVANCE_DISTANCE_THRESHOLD,
) -> Dict:
    """
    Combines retrieval-based and generation-based confidence signals
    into a single report. Set check_grounding=False to skip the extra
    LLM call and save quota during development/testing.
    """
    retrieval_confidence = compute_retrieval_confidence(chunks, distance_threshold=distance_threshold)

    if check_grounding:
        grounding = verify_answer_grounding(answer, chunks)
        grounding_verdict = grounding["verdict"]
        unsupported_claims = grounding["unsupported_claims"]
    else:
        grounding_verdict = "not_checked"
        unsupported_claims = []

    return {
        "retrieval_confidence": retrieval_confidence,
        "grounding_verdict": grounding_verdict,
        "unsupported_claims": unsupported_claims,
    }