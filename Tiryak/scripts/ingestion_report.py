"""
Dry-run ingestion report: parses and chunks every seed document exactly as
startup_seed.py would, but stops before embedding or writing to ChromaDB.

Prints, per document: chunk count, average token count, chunks flagged as
oversized (> CHUNK_MAX_TOKENS, kept — not dropped), chunks dropped as noise
(< CHUNK_DROP_TOKENS), and a few sample chunks so section boundaries can be
eyeballed before anything is actually indexed.

Usage (from the Tiryak/ directory):
    python -m scripts.ingestion_report
"""

from app.config import CHUNK_DROP_TOKENS, CHUNK_MAX_TOKENS
from app.embeddings.embedder import count_tokens
from app.startup_seed import SEED_DOCUMENTS, PARSERS

SAMPLES_PER_DOCUMENT = 3


def run_report():
    for seed in SEED_DOCUMENTS:
        print(f"\n{'=' * 70}")
        print(f"{seed['filename']}")
        print(f"{'=' * 70}")

        if not seed["file_path"].exists():
            print(f"  WARNING: file not found at {seed['file_path']} — skipping.")
            continue

        chunks = PARSERS[seed.get("parser", "generic")](seed["file_path"])
        if not chunks:
            print("  WARNING: parser produced 0 chunks.")
            continue

        drop_threshold = seed.get("drop_tokens", CHUNK_DROP_TOKENS)

        for c in chunks:
            c["_tokens"] = count_tokens(c["text"])

        dropped = [c for c in chunks if c["_tokens"] < drop_threshold]
        flagged = [c for c in chunks if c["_tokens"] > CHUNK_MAX_TOKENS]
        kept = [c for c in chunks if c["_tokens"] >= drop_threshold]

        avg_tokens = sum(c["_tokens"] for c in kept) / len(kept) if kept else 0

        print(f"  Total chunks parsed:        {len(chunks)}")
        print(f"  Chunks kept (>= {drop_threshold} tokens):  {len(kept)}")
        print(f"  Chunks dropped as noise (< {drop_threshold} tokens): {len(dropped)}")
        print(f"  Chunks flagged as oversized (> {CHUNK_MAX_TOKENS} tokens): {len(flagged)}")
        print(f"  Average token count (kept chunks): {avg_tokens:.1f}")

        if dropped:
            print(f"\n  Dropped chunks (noise):")
            for c in dropped[:5]:
                print(f"    - {c['_tokens']} tok | page {c['page_number']} | {c['text'][:60]!r}")

        if flagged:
            print(f"\n  Flagged chunks (oversized, kept anyway):")
            for c in flagged[:5]:
                print(f"    - {c['_tokens']} tok | page {c['page_number']} | section: {c.get('section_title')!r}")

        print(f"\n  --- {min(SAMPLES_PER_DOCUMENT, len(kept))} sample chunk(s) ---")
        step = max(len(kept) // SAMPLES_PER_DOCUMENT, 1)
        for c in kept[::step][:SAMPLES_PER_DOCUMENT]:
            print(f"\n  [page {c['page_number']}] section_title: {c.get('section_title')!r}")
            if c.get("disease_name"):
                print(f"  disease_name: {c['disease_name']!r}  category: {c.get('category')!r}")
            print(f"  tokens: {c['_tokens']}")
            preview = c["text"][:280].replace("\n", " | ")
            print(f"  text: {preview}{'...' if len(c['text']) > 280 else ''}")


if __name__ == "__main__":
    run_report()
