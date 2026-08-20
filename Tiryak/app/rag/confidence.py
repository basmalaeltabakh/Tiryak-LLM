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


def verify_answer_grounding(answer: str, chunks: List[Dict]) -> str:
    """
    Asks the LLM to double-check whether the generated answer is actually
    supported by the source chunks, as a second-pass sanity check.
    Returns one of: "grounded", "partially_grounded", "not_grounded".
    """
    context_text = "\n\n".join(
        f"[Page {c['page_number']}]\n{c['text']}" for c in chunks
    )

    verification_prompt = f"""You are verifying whether an answer is factually supported by the given sources.

Sources:
{context_text}

Answer to verify:
{answer}

Respond with exactly one word: "grounded" if the answer is fully supported by the sources, "partially_grounded" if only some of it is supported, or "not_grounded" if it isn't supported at all."""

    try:
        result = generate_content(verification_prompt)
    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=f"All AI providers are currently unavailable. Please try again later. ({str(e)})"
        )

    verdict = result["text"].strip().lower()

    if "not_grounded" in verdict:
        return "not_grounded"
    elif "partially_grounded" in verdict:
        return "partially_grounded"
    elif "grounded" in verdict:
        return "grounded"
    else:
        return "partially_grounded"


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
        grounding_verdict = verify_answer_grounding(answer, chunks)
    else:
        grounding_verdict = "not_checked"

    return {
        "retrieval_confidence": retrieval_confidence,
        "grounding_verdict": grounding_verdict
    }