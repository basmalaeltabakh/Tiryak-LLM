import shutil
import uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException

from app.config import UPLOADS_DIR
from app.ingestion.parsers import parse_document
from app.ingestion.chunker import chunk_document
from app.embeddings.embedder import embed_texts
from app.embeddings.vector_store import add_chunks_to_store, delete_document, list_all_documents

router = APIRouter()

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx"}


@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """
    Uploads a document, processes it (parse -> chunk -> embed -> store),
    and returns a document_id to use for querying it later.
    """
    extension = Path(file.filename).suffix.lower()

    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {extension}. Supported types: {SUPPORTED_EXTENSIONS}"
        )

    document_id = str(uuid.uuid4())
    saved_path = UPLOADS_DIR / f"{document_id}{extension}"

    # Save the uploaded file to disk
    with open(saved_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        # Run the full ingestion pipeline
        pages = parse_document(str(saved_path))
        chunks = chunk_document(pages)

        if not chunks:
            raise HTTPException(status_code=422, detail="No extractable text found in document.")

        texts = [c["text"] for c in chunks]
        embeddings = embed_texts(texts)

        add_chunks_to_store(chunks, embeddings, document_id=document_id, filename=file.filename)

    except Exception as e:
        # Clean up the saved file if processing failed
        saved_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Failed to process document: {str(e)}")

    return {
        "document_id": document_id,
        "filename": file.filename,
        "num_chunks": len(chunks),
        "status": "processed"
    }


@router.get("/list")
async def list_documents():
    """
    Returns all currently stored documents (document_id + filename),
    used by the frontend to let users select documents for multi-document queries.
    """
    return {"documents": list_all_documents()}


@router.delete("/{document_id}")
async def delete_document_endpoint(document_id: str):
    """
    Deletes a document's chunks from the vector store.
    """
    delete_document(document_id)
    return {"document_id": document_id, "status": "deleted"}