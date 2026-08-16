from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

from app.rag.pipeline import answer_question_safely
from app.config import TOP_K_RESULTS

router = APIRouter()


class QueryRequest(BaseModel):
    question: str
    document_ids: List[str] = []
    top_k: int = TOP_K_RESULTS
    check_grounding: bool = True
    user_type: str = "pharmacist"


@router.post("/ask")
async def ask_question(request: QueryRequest):
    """
    Answers a question through the shared safety pipeline. An empty
    document_ids list means "search across all indexed documents."
    """
    return answer_question_safely(
        question=request.question,
        document_ids=request.document_ids if request.document_ids else None,
        top_k=request.top_k,
        check_grounding=request.check_grounding,
        user_type=request.user_type
    )