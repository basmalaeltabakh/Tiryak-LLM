"""
Quick retrieval sanity check against the live ChromaDB index — NOT the
labeled evaluation set. Runs a handful of direct queries and prints the
top-3 retrieved chunks for each with their similarity score, so retrieval
quality can be eyeballed before building anything more formal on top of it.

Usage (from the Tiryak/ directory):
    python -m scripts.retrieval_smoke_test
"""

from app.rag.retriever import retrieve_relevant_chunks

TOP_K = 3
FLAG_BELOW_SIMILARITY = 0.70

QUERIES = [
    "ibuprofen hypertension risk",
    "first line treatment hypertension diuretic dose",
    "amoxicillin dose community acquired pneumonia adult",
    "stopping antidepressants withdrawal",
    "metformin type 2 diabetes elderly",
]


def run_smoke_test():
    flagged_queries = []

    for query in QUERIES:
        print(f"\n{'=' * 70}")
        print(f"Query: {query!r}")
        print(f"{'=' * 70}")

        results = retrieve_relevant_chunks(query, top_k=TOP_K, document_ids=None)

        for rank, r in enumerate(results, start=1):
            # ChromaDB's "cosine" space reports distance = 1 - cosine_similarity,
            # so similarity is recovered as 1 - distance.
            similarity = 1 - r["distance"]
            preview = r["text"][:120].replace("\n", " | ")
            print(f"  #{rank}  similarity={similarity:.4f}")
            print(f"       document_name: {r['filename']}")
            print(f"       section_title: {r.get('section_title')!r}")
            print(f"       text: {preview}")

            if rank == 1 and similarity < FLAG_BELOW_SIMILARITY:
                flagged_queries.append((query, similarity))

    print(f"\n{'=' * 70}")
    if flagged_queries:
        print("FLAGGED — top-1 similarity below 0.70 (retrieval may need attention):")
        for query, sim in flagged_queries:
            print(f"  - {query!r}: {sim:.4f}")
    else:
        print("No queries flagged — every top-1 result is at or above 0.70 similarity.")


if __name__ == "__main__":
    run_smoke_test()
