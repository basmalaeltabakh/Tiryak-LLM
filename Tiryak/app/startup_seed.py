from app.config import BASE_DIR
from app.ingestion.parsers import parse_document
from app.ingestion.chunker import chunk_document
from app.embeddings.embedder import embed_texts
from app.embeddings.vector_store import add_chunks_to_store, list_all_documents

SEED_DIR = BASE_DIR / "data" / "seed_documents"

SEED_DOCUMENTS = [
    {
        "document_id": "seed_polypharmacy_guide",
        "filename": "Polypharmacy in Older People (AWTTC, 2023).pdf",
        "file_path": SEED_DIR / "polypharmacy_guide.pdf",
    },
]


def ensure_seed_documents_loaded():
    """
    Runs once at backend startup. Ensures the core reference guideline(s)
    are always indexed, so the app has a working knowledge base without
    requiring a manual upload every session.
    """
    existing_ids = {doc["document_id"] for doc in list_all_documents()}

    for seed in SEED_DOCUMENTS:
        if seed["document_id"] in existing_ids:
            print(f"[seed] '{seed['filename']}' already indexed, skipping.")
            continue

        if not seed["file_path"].exists():
            print(f"[seed] WARNING: seed file not found at {seed['file_path']}, skipping.")
            continue

        print(f"[seed] Ingesting '{seed['filename']}'...")
        pages = parse_document(str(seed["file_path"]))
        chunks = chunk_document(pages)
        texts = [c["text"] for c in chunks]
        embeddings = embed_texts(texts)
        add_chunks_to_store(chunks, embeddings, document_id=seed["document_id"], filename=seed["filename"])
        print(f"[seed] Done — {len(chunks)} chunks indexed.")