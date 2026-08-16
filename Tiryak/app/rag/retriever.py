from typing import List, Dict, Optional
from app.embeddings.embedder import embed_single_text
from app.embeddings.vector_store import query_store


def retrieve_relevant_chunks(query: str, top_k: int = 5, document_ids: Optional[List[str]] = None) -> List[Dict]:
    """
    Given a user query, retrieves the most relevant chunks from the vector store.
    Can search within a single document, multiple specific documents, or all
    documents (if document_ids is None).

    Returns a list of dicts:
    {
        "text": str,
        "page_number": int,
        "chunk_id": str,
        "filename": str,
        "document_id": str,
        "distance": float
    }
    """
    query_vector = embed_single_text(query)
    results = query_store(query_vector, top_k=top_k, document_ids=document_ids)

    retrieved = []
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    for doc, meta, distance in zip(documents, metadatas, distances):
        retrieved.append({
            "text": doc,
            "page_number": meta["page_number"],
            "chunk_id": meta["chunk_id"],
            "filename": meta.get("filename", meta["document_id"]),
            "document_id": meta["document_id"],
            "distance": distance
        })

    return retrieved