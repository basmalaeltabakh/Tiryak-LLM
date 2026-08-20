from typing import List, Dict
from fastapi import HTTPException
from app.rag.llm_provider import generate_content
from app.rag.language_utils import detect_language


CONFIDENCE_LANGUAGE_INSTRUCTIONS = {
    "high": "",  # normal tone — evidence is a strong match, no extra hedging needed
    "medium": (
        "8. The retrieved evidence is a MODERATE match for this question — hedge appropriately: use phrasing "
        "like \"the guideline indicates...\" rather than flatly asserting facts, and note if a source only "
        "partially addresses the question.\n"
    ),
    "low": (
        "8. The retrieved evidence is a WEAK match for this question — you must hedge explicitly. Open with a "
        "caveat that the available sources only touch on this indirectly / cover it incompletely, before giving "
        "whatever partial information they do support. Do not state anything with more confidence than the "
        "evidence actually warrants.\n"
    ),
}


def build_context_prompt(
    query: str, chunks: List[Dict], user_type: str = "pharmacist", retrieval_confidence: str = "high"
) -> str:
    context_blocks = []
    for i, chunk in enumerate(chunks, start=1):
        source_label = f"Document: {chunk['filename']}, Page {chunk['page_number']}"
        # Extra structure available on section-aware-parsed documents — helps
        # the model understand which disease/section a chunk covers; absent
        # (and silently skipped) for documents that don't set these fields.
        if chunk.get("disease_name"):
            source_label += f", Topic: {chunk['disease_name']}"
        elif chunk.get("topic_name"):
            source_label += f", Topic: {chunk['topic_name']}"
        if chunk.get("section_title"):
            source_label += f", Section: {chunk['section_title']}"
        context_blocks.append(f"[Source {i} - {source_label}]\n{chunk['text']}")
    context_text = "\n\n".join(context_blocks)

    num_unique_docs = len(set(c["filename"] for c in chunks))
    multi_doc_instruction = (
        "The sources come from multiple different documents. When comparing or synthesizing information "
        "across them, explicitly mention which document each piece of information comes from.\n"
        if num_unique_docs > 1 else ""
    )

    if user_type == "patient":
        audience_instruction = (
            "The person asking is a PATIENT, not a healthcare professional. Use clear, everyday language, "
            "avoid unexplained medical jargon, and close by recommending they confirm anything about "
            "their own medication with a pharmacist or doctor before acting on it.\n"
        )
    else:
        audience_instruction = (
            "The person asking is a healthcare professional (pharmacist). Standard clinical terminology is fine, "
            "but keep the answer scannable rather than dense.\n"
        )

    language = detect_language(query)
    if language == "ar":
        language_instruction = (
            "Respond in EGYPTIAN COLLOQUIAL ARABIC (اللهجة المصرية العامية) — the way a pharmacist or doctor "
            "would actually speak to someone in Egypt, NOT formal Modern Standard Arabic (فصحى). Keep it warm, "
            "direct, and easy to follow.\n"
        )
    else:
        language_instruction = "Respond in English.\n"

    prompt = f"""You are a helpful assistant that answers questions strictly based on the provided document excerpts below. Follow these rules:

1. Only use information from the provided sources. Do not use outside knowledge.
2. If the sources don't contain enough information to answer, say so clearly instead of guessing.
3. If the sources simply don't mention the specific drug, combination, or condition asked about, that is NOT evidence that no interaction/risk exists. Never phrase this as a clinical finding (e.g. "there is no interaction"). State plainly that the available sources don't address it.
4. After each claim in your answer, cite the source using this EXACT format: [Document Name, Page X] if the source has no section, or [Document Name, Section: Y, Page X] if it does — copy the document name, section, and page number directly from the "[Source N - ...]" label above each excerpt. Never invent a page number or cite a page that isn't in the sources above. Do NOT cite using just "[Source N]" or "[Source N, Page X]" — the document name must always be spelled out so the citation is readable on its own without cross-referencing the source list.
5. {language_instruction}6. {audience_instruction}{multi_doc_instruction}7. Structure your answer like this: start with a short 1-2 sentence direct answer, then (if useful) a few bullet points with specifics. Keep it concise and scannable — do NOT use multiple headers or long dense paragraphs. Do NOT use Markdown tables under any circumstances.
{CONFIDENCE_LANGUAGE_INSTRUCTIONS.get(retrieval_confidence, "")}

Sources:
{context_text}

Question: {query}

Answer:"""
    return prompt


def generate_answer(
    query: str,
    chunks: List[Dict],
    preferred_provider: str = None,
    user_type: str = "pharmacist",
    retrieval_confidence: str = "high",
) -> Dict:
    if not chunks:
        language = detect_language(query)
        no_info_msg = (
            "معنديش معلومة كافية في المصادر المتاحة عشان أجاوب على السؤال ده."
            if language == "ar" else
            "No relevant information was found in the document(s) to answer this question."
        )
        return {"answer": no_info_msg, "sources": [], "provider_used": None}

    prompt = build_context_prompt(query, chunks, user_type=user_type, retrieval_confidence=retrieval_confidence)

    try:
        result = generate_content(prompt, preferred_provider=preferred_provider)
    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=f"All AI providers are currently unavailable. Please try again later. ({str(e)})"
        )

    return {
        "answer": result["text"],
        "sources": [
            {"page_number": c["page_number"], "chunk_id": c["chunk_id"], "filename": c["filename"], "document_id": c["document_id"]}
            for c in chunks
        ],
        "provider_used": result["provider_used"]
    }