from typing import List, Dict, Optional
from app.rag.retriever import retrieve_relevant_chunks
from app.rag.generator import generate_answer
from app.rag.confidence import get_confidence_report
from app.rag.language_utils import detect_language
from app.safety.guardrails import (
    classify_query_risk,
    get_refusal_response,
    check_retrieval_sufficiency,
    get_insufficient_evidence_response,
    SAFETY_DISCLAIMER,
)
from app.config import CLINICAL_TOPIC, TOP_K_RESULTS


def answer_question_safely(
    question: str,
    document_ids: Optional[List[str]],
    top_k: int = TOP_K_RESULTS,
    check_grounding: bool = True,
    user_type: str = "pharmacist"
) -> Dict:
    language = detect_language(question)

    risk = classify_query_risk(question, CLINICAL_TOPIC, user_type=user_type)

    if risk.get("risk_level") == "refuse":
        return {**get_refusal_response(risk.get("reasoning", ""), language=language), "question": question}

    chunks = retrieve_relevant_chunks(query=question, top_k=top_k, document_ids=document_ids)

    if not check_retrieval_sufficiency(chunks):
        return {**get_insufficient_evidence_response(language=language), "question": question}

    result = generate_answer(question, chunks, user_type=user_type)

    confidence = get_confidence_report(result["answer"], chunks, check_grounding=check_grounding)

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
        for c in chunks
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