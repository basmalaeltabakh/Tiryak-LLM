import chromadb
from typing import List, Dict
from app.config import CHROMA_DIR, COLLECTION_NAME, EMBEDDING_MODEL_NAME


_client = None
_collection = None


def get_client():
    """
    Lazy-loads a persistent ChromaDB client that saves data to disk.
    """
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return _client


def get_collection():
    """
    Gets or creates the collection used to store document chunks.
    Uses cosine distance instead of the default L2, since it's more
    standard for semantic similarity search.

    The collection records which embedding model it was built with. If the
    configured EMBEDDING_MODEL_NAME ever changes (e.g. swapping embedding
    models), stored and freshly-computed vectors would sit in different,
    incompatible vector spaces — same dimensionality doesn't mean same
    space, so a dimension check alone wouldn't catch this, and retrieval
    would silently return wrong results with no error. Detected here by
    comparing against the collection's own metadata, and the collection is
    dropped and rebuilt automatically rather than mixing the two.
    """
    global _collection
    if _collection is None:
        client = get_client()
        existing_names = {c.name for c in client.list_collections()}

        if COLLECTION_NAME in existing_names:
            existing = client.get_collection(name=COLLECTION_NAME)
            stored_model = (existing.metadata or {}).get("embedding_model")
            if stored_model != EMBEDDING_MODEL_NAME:
                print(
                    f"[vector_store] Collection was built with embedding model "
                    f"'{stored_model}', but config now specifies "
                    f"'{EMBEDDING_MODEL_NAME}'. Wiping and rebuilding the "
                    f"collection to avoid mixing incompatible vector spaces."
                )
                client.delete_collection(name=COLLECTION_NAME)
                existing_names.discard(COLLECTION_NAME)

        if COLLECTION_NAME in existing_names:
            _collection = client.get_collection(name=COLLECTION_NAME)
        else:
            _collection = client.create_collection(
                name=COLLECTION_NAME,
                metadata={"hnsw:space": "cosine", "embedding_model": EMBEDDING_MODEL_NAME}
            )
    return _collection


# Optional per-chunk metadata a parser may attach beyond the base fields below.
# Populated by the section-aware parsers (app/ingestion/chunker.py for generic
# documents, aware_parser.py, hearts_parser.py); any chunk missing a key here
# simply doesn't get it attached (Chroma rejects None values), so documents
# that don't set every field stay backward compatible.
OPTIONAL_CHUNK_METADATA_KEYS = ("section_title", "topic_name", "disease_name", "category", "is_front_matter")


def add_chunks_to_store(
    chunks: List[Dict],
    embeddings: List[List[float]],
    document_id: str,
    filename: str = None,
    source_url: str = None,
):
    """
    Stores chunks + their embeddings in ChromaDB.

    chunks: list of {"chunk_id": str, "text": str, "page_number": int}, optionally
            with any of OPTIONAL_CHUNK_METADATA_KEYS for richer citations/filtering
    embeddings: list of vectors, same order and length as chunks
    document_id: identifies which document these chunks belong to
    filename: original filename (used as document_name in citations/evidence panel),
              stored so multi-document answers can reference documents by name
              instead of raw IDs
    source_url: canonical URL for the source document, if known — constant
                across every chunk of this document, same as filename
    """
    collection = get_collection()

    ids = [f"{document_id}_{chunk['chunk_id']}" for chunk in chunks]
    documents = [chunk["text"] for chunk in chunks]
    metadatas = []
    for chunk in chunks:
        meta = {
            "document_id": document_id,
            "filename": filename or document_id,
            "page_number": chunk["page_number"],
            "chunk_id": chunk["chunk_id"]
        }
        if source_url:
            meta["source_url"] = source_url
        # Chroma rejects None metadata values, so only attach keys the parser
        # actually populated (existing chunks without these keys are unaffected).
        for key in OPTIONAL_CHUNK_METADATA_KEYS:
            if chunk.get(key):
                meta[key] = chunk[key]
        metadatas.append(meta)

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas
    )


def query_store(
    query_embedding: List[float],
    top_k: int = 5,
    document_ids: List[str] = None,
    exclude_front_matter: bool = False,
) -> Dict:
    """
    Searches the vector store for the most relevant chunks to a query embedding.
    Optionally restrict the search to one or more document_ids.

    document_ids: list of document IDs to search within. None means search
                  across all documents.
    exclude_front_matter: when True, excludes chunks tagged is_front_matter=True
                  (currently only set by hearts_parser.py for cover/TOC-style
                  pages). Chunks that never set this key at all — every other
                  document — are unaffected: "$ne: True" only matches away the
                  chunks explicitly flagged, not ones missing the field
                  (verified directly against Chroma's actual filter behavior).
    """
    collection = get_collection()

    clauses = []
    if document_ids:
        if len(document_ids) == 1:
            clauses.append({"document_id": document_ids[0]})
        else:
            clauses.append({"document_id": {"$in": document_ids}})
    if exclude_front_matter:
        clauses.append({"is_front_matter": {"$ne": True}})

    if not clauses:
        where_filter = None
    elif len(clauses) == 1:
        where_filter = clauses[0]
    else:
        where_filter = {"$and": clauses}

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where_filter
    )
    return results


def list_all_documents() -> List[Dict]:
    """
    Returns a list of all unique documents currently stored, with their
    document_id and filename, so the frontend can let users pick which
    documents to query across.
    """
    collection = get_collection()
    results = collection.get()

    seen = {}
    for meta in results["metadatas"]:
        doc_id = meta["document_id"]
        if doc_id not in seen:
            seen[doc_id] = meta.get("filename", doc_id)

    return [{"document_id": doc_id, "filename": filename} for doc_id, filename in seen.items()]


def delete_document(document_id: str):
    """
    Removes all chunks belonging to a specific document from the store.
    Useful when a user re-uploads or deletes a document.
    """
    collection = get_collection()
    collection.delete(where={"document_id": document_id})