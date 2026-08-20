"""
Unified evaluation: retrieval Precision@k + generation faithfulness/answer
relevancy/context relevancy + citation accuracy, computed together against
the same labeled question set and saved to one log — as opposed to
scripts/run_eval.py (retrieval only) and the /evaluation/run endpoint
(generation only, unreachable from the frontend), which were previously two
disconnected tools that never got run together.

Costs real LLM calls (~4 per question: generation + 3 evaluator judgments).
Defaults to a small subset to keep that bounded; pass --limit to change it,
or --limit 0 for the full labeled set.

Usage (from the Tiryak/ directory):
    python -m scripts.run_full_eval [--limit N]
"""

import argparse
import json
from pathlib import Path

from fastapi import HTTPException

from app.rag.retriever import retrieve_relevant_chunks
from app.rag.generator import generate_answer
from app.evaluation.evaluator import evaluate_answer
from app.rag.citation_validator import validate_citations
from scripts.run_eval import _precision_at_k

EVAL_SET_PATH = Path(__file__).parent / "eval_set.json"
RESULTS_PATH = Path(__file__).parent / "full_eval_results.json"
TOP_K = 5
DEFAULT_LIMIT = 6


def run_full_eval(limit: int = DEFAULT_LIMIT):
    eval_set = json.loads(EVAL_SET_PATH.read_text(encoding="utf-8"))
    scorable = [item for item in eval_set if item["expected_source_pages"]]
    if limit:
        scorable = scorable[:limit]

    rows = []
    skipped = []
    for item in scorable:
        try:
            chunks = retrieve_relevant_chunks(
                item["question"], top_k=TOP_K, document_ids=None, exclude_front_matter=True
            )
            p_at_3 = round(_precision_at_k(chunks, item, 3), 4)
            p_at_5 = round(_precision_at_k(chunks, item, 5), 4)

            result = generate_answer(item["question"], chunks)
            answer = result["answer"]

            generation_eval = evaluate_answer(item["question"], answer, chunks)
            citation_report = validate_citations(answer, chunks)
        except HTTPException as e:
            # A provider outage/quota exhaustion mid-run shouldn't discard
            # every result collected so far — log it, skip this question,
            # keep going, and still save whatever was completed.
            print(f"[SKIP] {item['id']:5s} provider error: {e.detail}")
            skipped.append({"id": item["id"], "question": item["question"], "error": str(e.detail)})
            continue

        rows.append({
            "id": item["id"],
            "category": item["category"],
            "question": item["question"],
            "p_at_3": p_at_3,
            "p_at_5": p_at_5,
            "faithfulness": generation_eval["faithfulness"].get("score"),
            "answer_relevancy": generation_eval["answer_relevancy"].get("score"),
            "context_relevancy": generation_eval["context_relevancy"].get("score"),
            "citation_accuracy": citation_report["citation_accuracy"],
            "num_citations": citation_report["num_citations"],
            "invalid_citations": citation_report["invalid_citations"],
            "provider_used": result["provider_used"],
            "answer": answer,
        })
        mark = "OK" if p_at_3 > 0 else "--"
        print(f"[{mark}] {item['id']:5s} P@3={p_at_3:.2f} faithfulness={rows[-1]['faithfulness']} "
              f"citation_acc={rows[-1]['citation_accuracy']}  {item['question'][:55]}")

    def _mean(key):
        vals = [r[key] for r in rows if r[key] is not None]
        return round(sum(vals) / len(vals), 3) if vals else None

    summary = {
        "questions_evaluated": len(rows),
        "questions_skipped": len(skipped),
        "mean_p_at_3": _mean("p_at_3"),
        "mean_p_at_5": _mean("p_at_5"),
        "mean_faithfulness": _mean("faithfulness"),
        "mean_answer_relevancy": _mean("answer_relevancy"),
        "mean_context_relevancy": _mean("context_relevancy"),
        "mean_citation_accuracy": _mean("citation_accuracy"),
    }

    print("\n--- Unified evaluation summary ---")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    if skipped:
        print(f"\n{len(skipped)} question(s) skipped due to provider errors — see 'skipped' in the saved log.")

    RESULTS_PATH.write_text(
        json.dumps({"summary": summary, "rows": rows, "skipped": skipped}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nResults saved to {RESULTS_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Number of questions to evaluate (0 = full set)")
    args = parser.parse_args()
    run_full_eval(limit=args.limit)
