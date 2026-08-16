from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.routes_summary import get_all_chunks_for_document
from app.advanced.entity_extractor import extract_entities, extract_tables

router = APIRouter()


class ExtractionRequest(BaseModel):
    document_id: str


@router.post("/entities")
async def get_entities(request: ExtractionRequest):
    """
    Extracts named entities (people, organizations, dates, monetary amounts,
    percentages) from a document.
    """
    chunks = get_all_chunks_for_document(request.document_id)

    if not chunks:
        raise HTTPException(status_code=404, detail="Document not found or has no chunks.")

    entities = extract_entities(chunks)

    return {
        "document_id": request.document_id,
        "entities": entities
    }


@router.post("/tables")
async def get_tables(request: ExtractionRequest):
    """
    Extracts tabular data (pricing tables, schedules, comparison tables, etc.)
    from a document.
    """
    chunks = get_all_chunks_for_document(request.document_id)

    if not chunks:
        raise HTTPException(status_code=404, detail="Document not found or has no chunks.")

    tables = extract_tables(chunks)

    return {
        "document_id": request.document_id,
        "tables": tables.get("tables", [])
    }