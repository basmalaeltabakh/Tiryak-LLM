from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional

from app.rag.pipeline import answer_question_safely
from app.config import TOP_K_RESULTS

router = APIRouter()


class QueryRequest(BaseModel):
    question: str
    retrieval_query: Optional[str] = None
    document_ids: List[str] = []
    top_k: int = TOP_K_RESULTS
    check_grounding: bool = True
    user_type: str = "pharmacist"


@router.post("/ask")
async def ask_question(request: QueryRequest):
    """
    Answers a question through the shared safety pipeline. An empty
    document_ids list means "search across all indexed documents."

    retrieval_query: optional plain-text version of the question, used for
    vector search instead of `question`. Callers that prepend patient-context
    or instruction boilerplate to `question` (e.g. the Streamlit frontend)
    should pass the original, unmodified question here — embedding that
    boilerplate alongside the real question measurably degrades retrieval
    (verified: it pulled in closer-but-still-irrelevant chunks in testing).
    `question` still goes to the LLM in full, so context isn't lost.
    """
    return answer_question_safely(
        question=request.question,
        retrieval_query=request.retrieval_query,
        document_ids=request.document_ids if request.document_ids else None,
        top_k=request.top_k,
        check_grounding=request.check_grounding,
        user_type=request.user_type
    )