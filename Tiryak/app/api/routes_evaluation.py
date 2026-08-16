from typing import List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.rag.retriever import retrieve_relevant_chunks
from app.rag.generator import generate_answer
from app.evaluation.evaluator import evaluate_answer
from app.config import TOP_K_RESULTS

router = APIRouter()


class EvaluationRequest(BaseModel):
    document_ids: List[str]
    test_questions: List[str]
    top_k: int = TOP_K_RESULTS


@router.post("/run")
async def run_evaluation(request: EvaluationRequest):
    """
    Runs a batch of test questions through the full RAG pipeline
    (retrieve -> generate) and evaluates each answer on faithfulness,
    answer relevancy, and context relevancy. Returns per-question
    results plus averaged scores across the whole batch.
    """
    if not request.test_questions:
        raise HTTPException(status_code=400, detail="Provide at least one test question.")

    per_question_results = []

    for question in request.test_questions:
        chunks = retrieve_relevant_chunks(
            query=question,
            top_k=request.top_k,
            document_ids=request.document_ids
        )

        result = generate_answer(question, chunks)
        evaluation = evaluate_answer(question, result["answer"], chunks)

        per_question_results.append({
            "question": question,
            "answer": result["answer"],
            "provider_used": result["provider_used"],
            "evaluation": evaluation
        })

    def _avg(metric_name: str) -> float:
        scores = [
            r["evaluation"][metric_name]["score"]
            for r in per_question_results
            if r["evaluation"][metric_name].get("score") is not None
        ]
        return round(sum(scores) / len(scores), 3) if scores else None

    summary = {
        "avg_faithfulness": _avg("faithfulness"),
        "avg_answer_relevancy": _avg("answer_relevancy"),
        "avg_context_relevancy": _avg("context_relevancy"),
        "num_questions_evaluated": len(per_question_results)
    }

    return {
        "summary": summary,
        "per_question_results": per_question_results
    }