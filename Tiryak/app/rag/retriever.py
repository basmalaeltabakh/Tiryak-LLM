from typing import List, Dict, Optional

from app.embeddings.embedder import embed_single_text
from app.embeddings.vector_store import query_store, OPTIONAL_CHUNK_METADATA_KEYS


def retrieve_relevant_chunks(
    query: str,
    top_k: int = 5,
    document_ids: Optional[List[str]] = None,
    exclude_front_matter: bool = False,
) -> List[Dict]:
    """
    Given a user query, retrieves the most relevant chunks from the vector store.
    Can search within a single document, multiple specific documents, or all
    documents (if document_ids is None).

    exclude_front_matter: skip chunks tagged is_front_matter=True (currently
        only cover/TOC-style HEARTS pages — see hearts_parser.py). Defaults
        to False so existing callers (the pipeline) are unaffected; a query
        builder for clinical questions should pass True.

    Returns a list of dicts:
    {
        "text": str,
        "page_number": int,
        "chunk_id": str,
        "filename": str,
        "document_id": str,
        "distance": float,
        "source_url": Optional[str],
        # plus any of OPTIONAL_CHUNK_METADATA_KEYS the source parser populated
        # (e.g. "section_title", "topic_name", "disease_name", "category")
    }
    """
    query_vector = embed_single_text(query)
    results = query_store(
        query_vector,
        top_k=top_k,
        document_ids=document_ids,
        exclude_front_matter=exclude_front_matter,
    )

    retrieved = []
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    for doc, meta, distance in zip(documents, metadatas, distances):
        chunk = {
            "text": doc,
            "page_number": meta["page_number"],
            "chunk_id": meta["chunk_id"],
            "filename": meta.get("filename", meta["document_id"]),
            "document_id": meta["document_id"],
            "distance": distance,
            "source_url": meta.get("source_url"),
        }
        for key in OPTIONAL_CHUNK_METADATA_KEYS:
            if key in meta:
                chunk[key] = meta[key]
        retrieved.append(chunk)

    return retrieved
