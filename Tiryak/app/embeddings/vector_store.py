import chromadb
from typing import List, Dict
from app.config import CHROMA_DIR, COLLECTION_NAME


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
    """
    global _collection
    if _collection is None:
        client = get_client()
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )
    return _collection


def add_chunks_to_store(chunks: List[Dict], embeddings: List[List[float]], document_id: str, filename: str = None):
    """
    Stores chunks + their embeddings in ChromaDB.

    chunks: list of {"chunk_id": str, "text": str, "page_number": int}
    embeddings: list of vectors, same order and length as chunks
    document_id: identifies which document these chunks belong to
    filename: original filename, stored so multi-document answers can
              reference documents by name instead of raw IDs
    """
    collection = get_collection()

    ids = [f"{document_id}_{chunk['chunk_id']}" for chunk in chunks]
    documents = [chunk["text"] for chunk in chunks]
    metadatas = [
        {
            "document_id": document_id,
            "filename": filename or document_id,
            "page_number": chunk["page_number"],
            "chunk_id": chunk["chunk_id"]
        }
        for chunk in chunks
    ]

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas
    )


def query_store(query_embedding: List[float], top_k: int = 5, document_ids: List[str] = None) -> Dict:
    """
    Searches the vector store for the most relevant chunks to a query embedding.
    Optionally restrict the search to one or more document_ids.

    document_ids: list of document IDs to search within. None means search
                  across all documents.
    """
    collection = get_collection()

    where_filter = None
    if document_ids:
        if len(document_ids) == 1:
            where_filter = {"document_id": document_ids[0]}
        else:
            where_filter = {"document_id": {"$in": document_ids}}

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