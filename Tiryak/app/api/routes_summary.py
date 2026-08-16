from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.embeddings.vector_store import get_collection
from app.advanced.summarizer import summarize_document

router = APIRouter()


class SummaryRequest(BaseModel):
    document_id: str


def get_all_chunks_for_document(document_id: str):
    """
    Retrieves all stored chunks for a given document from ChromaDB,
    ordered by page number.
    """
    collection = get_collection()
    results = collection.get(where={"document_id": document_id})

    chunks = []
    for doc, meta in zip(results["documents"], results["metadatas"]):
        chunks.append({
            "text": doc,
            "page_number": meta["page_number"],
            "chunk_id": meta["chunk_id"]
        })

    # Sort by page number so the summary follows the document's natural order
    chunks.sort(key=lambda c: c["page_number"])
    return chunks


@router.post("/generate")
async def generate_summary(request: SummaryRequest):
    """
    Generates a hierarchical summary (per-chunk + final combined) for a document.
    """
    chunks = get_all_chunks_for_document(request.document_id)

    if not chunks:
        raise HTTPException(status_code=404, detail="Document not found or has no chunks.")

    result = summarize_document(chunks)

    return {
        "document_id": request.document_id,
        "final_summary": result["final_summary"],
        "chunk_summaries": result["chunk_summaries"]
    }