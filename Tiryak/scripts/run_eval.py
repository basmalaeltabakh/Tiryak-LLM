"""
Precision@K evaluation against scripts/eval_set.json, run directly against
the retriever (no generator/pipeline involved — retrieval verification only,
same scope as the smoke test).

Usage (from the Tiryak/ directory):
    python -m scripts.run_eval
"""

import json
from pathlib import Path

from app.rag.retriever import retrieve_relevant_chunks

EVAL_SET_PATH = Path(__file__).parent / "eval_set.json"
RESULTS_PATH = Path(__file__).parent / "eval_results.json"
TOP_K = 5


def _is_relevant(chunk: dict, item: dict) -> bool:
    if chunk["page_number"] not in item["expected_source_pages"]:
        return False
    expected_docs = {item["expected_document"]}
    if item.get("expected_document_secondary"):
        expected_docs.add(item["expected_document_secondary"])
    return chunk["filename"] in expected_docs


def _precision_at_k(results: list, item: dict, k: int) -> float:
    top_k = results[:k]
    if not top_k:
        return 0.0
    relevant = sum(1 for c in top_k if _is_relevant(c, item))
    return relevant / len(top_k)


def run_eval():
    eval_set = json.loads(EVAL_SET_PATH.read_text())

    scored_rows = []
    refusal_rows = []
    failures = []

    for item in eval_set:
        results = retrieve_relevant_chunks(
            item["question"], top_k=TOP_K, document_ids=None, exclude_front_matter=True
        )
        top = results[0] if results else None
        top_similarity = round(1 - top["distance"], 4) if top else None

        if not item["expected_source_pages"]:
            refusal_rows.append({
                "id": item["id"],
                "question": item["question"],
                "top_document": top["filename"] if top else None,
                "top_section_title": top.get("section_title") if top else None,
                "top_similarity": top_similarity,
            })
            continue

        p_at_3 = round(_precision_at_k(results, item, 3), 4)
        p_at_5 = round(_precision_at_k(results, item, 5), 4)

        scored_rows.append({
            "id": item["id"],
            "category": item["category"],
            "question": item["question"],
            "p_at_3": p_at_3,
            "p_at_5": p_at_5,
            "top_document": top["filename"] if top else None,
            "top_similarity": top_similarity,
            "retrieved": [
                {
                    "rank": rank,
                    "similarity": round(1 - c["distance"], 4),
                    "document_name": c["filename"],
                    "section_title": c.get("section_title"),
                    "page_number": c["page_number"],
                    "relevant": _is_relevant(c, item),
                }
                for rank, c in enumerate(results, start=1)
            ],
        })

        if p_at_3 == 0.0:
            failures.append(scored_rows[-1])

    mean_p3 = sum(r["p_at_3"] for r in scored_rows) / len(scored_rows) if scored_rows else 0.0
    mean_p5 = sum(r["p_at_5"] for r in scored_rows) / len(scored_rows) if scored_rows else 0.0

    # --- print markdown table ---
    print("| id | category | P@3 | P@5 | top_document | top_score |")
    print("|---|---|---|---|---|---|")
    for r in scored_rows:
        doc_short = r["top_document"][:40] + "..." if r["top_document"] and len(r["top_document"]) > 40 else r["top_document"]
        print(f"| {r['id']} | {r['category']} | {r['p_at_3']:.2f} | {r['p_at_5']:.2f} | {doc_short} | {r['top_similarity']} |")

    print()
    print("--- Overall metrics ---")
    print(f"Mean P@3: {mean_p3:.4f}")
    print(f"Mean P@5: {mean_p5:.4f}")
    print(f"Questions scored: {len(scored_rows)}")
    print(f"Questions skipped (out-of-scope, refusal coverage): {len(refusal_rows)}")

    print()
    print("--- Refusal coverage (out-of-scope questions, not scored) ---")
    for r in refusal_rows:
        print(f"  {r['id']}: {r['question']!r}")
        print(f"    top retrieved anyway: {r['top_document']!r} | {r['top_section_title']!r} | similarity={r['top_similarity']}")

    print()
    if failures:
        print(f"--- FLAGGED: {len(failures)} question(s) with P@3 = 0.0 ---")
        for f in failures:
            print(f"\n  {f['id']}: {f['question']!r}")
            print(f"  Expected pages: (see eval_set.json) — got:")
            for r in f["retrieved"]:
                mark = "OK" if r["relevant"] else "--"
                print(f"    [{mark}] rank {r['rank']} sim={r['similarity']} | {r['document_name']} | page {r['page_number']} | {r['section_title']!r}")
    else:
        print("--- No questions flagged (all scored questions have P@3 > 0.0) ---")

    RESULTS_PATH.write_text(json.dumps({
        "mean_p_at_3": round(mean_p3, 4),
        "mean_p_at_5": round(mean_p5, 4),
        "questions_scored": len(scored_rows),
        "questions_skipped": len(refusal_rows),
        "scored": scored_rows,
        "refusal_coverage": refusal_rows,
        "failures": [f["id"] for f in failures],
    }, indent=2))
    print(f"\nResults saved to {RESULTS_PATH}")


if __name__ == "__main__":
    run_eval()
