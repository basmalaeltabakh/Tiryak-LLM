from typing import List, Dict
from fastapi import HTTPException
from app.rag.llm_provider import generate_content


def _safe_generate(prompt: str) -> str:
    """
    Wraps generate_content with quota/provider error handling,
    shared by all LLM calls in this module.
    """
    try:
        result = generate_content(prompt)
    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=f"All AI providers are currently unavailable. Please try again later. ({str(e)})"
        )
    return result["text"]


def summarize_chunks_batch(chunks: List[Dict], batch_size: int = 6) -> List[Dict]:
    """
    Summarizes chunks in batches instead of one-by-one, to reduce the number
    of LLM API calls and speed up the overall process significantly.
    Returns a list of {"page_range": str, "summary": str}.
    """
    batch_summaries = []

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]

        combined_text = "\n\n".join(
            f"[Page {c['page_number']}]\n{c['text']}" for c in batch
        )

        pages_in_batch = sorted(set(c["page_number"] for c in batch))
        page_range = f"{pages_in_batch[0]}-{pages_in_batch[-1]}" if len(pages_in_batch) > 1 else str(pages_in_batch[0])

        prompt = f"""Summarize the following document excerpts (pages {page_range}) into a concise paragraph (4-6 sentences) capturing the key points. Keep the same language as the original text (Arabic or English).

Text:
{combined_text}

Summary:"""

        summary_text = _safe_generate(prompt)
        batch_summaries.append({
            "page_range": page_range,
            "summary": summary_text
        })

    return batch_summaries


def summarize_document(chunks: List[Dict], batch_size: int = 6) -> Dict:
    """
    Full hierarchical summarization pipeline (optimized with batching):
    1. Summarize chunks in batches
    2. Combine batch summaries into one final document summary
    """
    batch_summaries = summarize_chunks_batch(chunks, batch_size=batch_size)

    combined_summaries = "\n".join(
        f"[Pages {bs['page_range']}] {bs['summary']}" for bs in batch_summaries
    )

    final_prompt = f"""Below are summaries of consecutive sections of a document, in order. Combine them into a single, coherent, well-structured summary of the entire document. Remove redundancy, keep the logical flow, and organize it with clear structure (use headings or bullet points if helpful). Respond in the same language as the text below (Arabic or English).

Section summaries:
{combined_summaries}

Full document summary:"""

    final_summary_text = _safe_generate(final_prompt)

    return {
        "final_summary": final_summary_text,
        "chunk_summaries": batch_summaries
    }