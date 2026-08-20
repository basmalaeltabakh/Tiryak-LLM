from typing import List, Dict, Optional
from app.rag.retriever import retrieve_relevant_chunks
from app.rag.generator import generate_answer
from app.rag.confidence import get_confidence_report
from app.rag.language_utils import detect_language, translate_query_to_english
from app.safety.guardrails import (
    classify_query_risk,
    get_refusal_response,
    filter_relevant_chunks,
    get_insufficient_evidence_response,
    SAFETY_DISCLAIMER,
)
from app.config import (
    CLINICAL_TOPIC,
    TOP_K_RESULTS,
    CHUNK_RELEVANCE_DISTANCE_THRESHOLD,
    CHUNK_RELEVANCE_DISTANCE_THRESHOLD_AR,
)


def answer_question_safely(
    question: str,
    document_ids: Optional[List[str]],
    top_k: int = TOP_K_RESULTS,
    check_grounding: bool = True,
    user_type: str = "pharmacist",
    retrieval_query: Optional[str] = None,
) -> Dict:
    """
    retrieval_query: plain-text question to embed for vector search, if it
    differs from `question` (e.g. a caller that prepends patient-context or
    instruction boilerplate to `question` for generation should pass the
    original clean text here). Defaults to `question` when not given.
    """
    language = detect_language(question)

    risk = classify_query_risk(question, CLINICAL_TOPIC, user_type=user_type)

    if risk.get("risk_level") == "refuse":
        return {**get_refusal_response(risk.get("reasoning", ""), language=language), "question": question}

    raw_retrieval_query = retrieval_query or question
    embedding_query = raw_retrieval_query
    relevance_threshold = CHUNK_RELEVANCE_DISTANCE_THRESHOLD
    if language == "ar":
        # The corpus is entirely English-source text, so an Arabic query is a
        # cross-lingual match against it, and this embedding model scores
        # that systematically worse than a same-language query for identical
        # content (measured: ~0.06-0.10 higher distance, and for several real
        # queries the correct page fell out of the top-25 results entirely —
        # no distance threshold or top_k tuning fixes that). Translating to
        # English first turns retrieval into an English-to-English match,
        # which measurably finds the right content instead of just tolerating
        # the gap with a looser cutoff.
        translated = translate_query_to_english(raw_retrieval_query)
        if translated:
            embedding_query = translated
        else:
            # All LLM providers unavailable — fall back to embedding the
            # Arabic text directly with the wider Arabic-calibrated cutoff,
            # rather than failing the whole request.
            relevance_threshold = CHUNK_RELEVANCE_DISTANCE_THRESHOLD_AR

    chunks = retrieve_relevant_chunks(
        query=embedding_query, top_k=top_k, document_ids=document_ids, exclude_front_matter=True
    )
    relevant_chunks = filter_relevant_chunks(chunks, distance_threshold=relevance_threshold)

    if not relevant_chunks:
        return {**get_insufficient_evidence_response(language=language), "question": question}

    result = generate_answer(question, relevant_chunks, user_type=user_type)

    confidence = get_confidence_report(
        result["answer"], relevant_chunks, check_grounding=check_grounding, distance_threshold=relevance_threshold
    )

    final_answer = result["answer"]
    if risk.get("risk_level") == "needs_caution":
        caveat = (
            "\n\n⚠️ السؤال ده خاص بحالة معينة — يفضل تتأكد مع صيدلي أو دكتور قبل ما تتصرف بناءً عليه."
            if language == "ar" else
            "\n\n⚠️ This involves a specific personal scenario — please verify with a pharmacist or doctor before acting."
        )
        final_answer += caveat
    final_answer += f"\n\n{SAFETY_DISCLAIMER.get(language, SAFETY_DISCLAIMER['en'])}"

    evidence_panel = [
        {
            "filename": c["filename"],
            "page_number": c["page_number"],
            "text_snippet": c["text"][:300] + ("..." if len(c["text"]) > 300 else ""),
            "similarity_distance": round(c["distance"], 4),
            # Present only for documents whose parser tags chunks with these
            # (all three section-aware parsers now do); omitted otherwise.
            **({"section_title": c["section_title"]} if c.get("section_title") else {}),
            **({"disease_name": c["disease_name"]} if c.get("disease_name") else {}),
            **({"category": c["category"]} if c.get("category") else {}),
            **({"source_url": c["source_url"]} if c.get("source_url") else {}),
        }
        for c in relevant_chunks
    ]

    return {
        "question": question,
        "answer": final_answer,
        "sources": result["sources"],
        "evidence_panel": evidence_panel,
        "confidence": confidence,
        "provider_used": result["provider_used"],
        "safety": risk
    }