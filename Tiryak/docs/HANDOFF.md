# Tiryak — Retrieval Layer Handoff

## 1. Completed
- Embedding model switched to intfloat/multilingual-e5-base (512-token window)
- Query/passage prefix convention live in embedder.py only, never stored in chunk text
- ChromaDB auto-wipe on embedding-model mismatch (vector_store.py)
- Generic chunker.py rewritten: heading detection, boilerplate stripping, TOC-page skip, shared pack_sections_into_chunks / split_text_by_tokens utilities
- Dedicated aware_parser.py built for WhoAware.pdf (two-column infographic layout)
- Dedicated hearts_parser.py built for WhoHearts.pdf (step-flowchart + dose table + side panel layout)
- Per-chunk metadata standardized: document_name, page_number, section_title, chunk_id, source_url, category, disease_name, topic_name
- Per-document drop-token threshold override (WhoAware = 20, others = 80)
- is_front_matter flag added for WhoHearts pages 1-13; exclude_front_matter param added through retriever.py and vector_store.py
- BM25 re-ranking implemented, tested, found to regress Precision@3, reverted back to pure semantic search
- Eval harness built: scripts/eval_set.json (20 labeled questions), scripts/run_eval.py, scripts/ingestion_report.py, scripts/retrieval_smoke_test.py
- Root-cause ligature bug fixed in hearts_parser.py (fi/fl glyph inconsistency was silently breaking a title-dedup check)
- section_title now prepended into the embedded/stored chunk text (pack_sections_into_chunks in chunker.py), with doubling-avoidance for parsers that already inline a title bracket

## 2. Current Metrics
- Baseline (pure semantic search, section_title NOT in embedded text): Mean P@3 = 0.4706, Mean P@5 = 0.3412 (17 scored questions, 3 out-of-scope skipped)
- BM25 re-rank variant (reverted, not adopted): Mean P@3 = 0.2745, Mean P@5 = 0.2706
- Post section_title-prepending: not yet measured

## 3. In Progress Right Now
- ChromaDB collection was wiped and re-indexing of all 3 documents (with section_title now embedded) was mid-run when work was halted
- run_eval.py has not yet been run against the new index
- Old-vs-new Precision@3 comparison table has not been produced

## 4. Remaining (Ordered)
1. Confirm the in-progress reindex finished (expected chunk counts: Polypharmacy 65, WhoAware ~347, HEARTS 62)
2. Re-run scripts/run_eval.py against the freshly reindexed collection
3. Compare new Mean P@3 / P@5 against the 0.4706 / 0.3412 baseline
4. If Mean P@3 still below the 0.65 target, diagnose remaining failures and propose one targeted fix
5. Build the query-builder layer (not started) — should set exclude_front_matter=True for clinical queries
6. Decide whether the AWaRe repeated-bracket cosmetic issue (13/348 chunks) is worth fixing
7. Decide whether to keep or remove rank-bm25 from requirements.txt

## 5. Known Issues / Bugs to Watch
- rank-bm25 remains listed in requirements.txt though the re-ranking code was reverted — dead dependency
- 13/348 WhoAware chunks have a cosmetically repeated section bracket (two same-named subsections merged, each keeping its own inline bracket) — pre-existing, not caused by the section_title change, low priority
- polypharmacy_guide.pdf.pdf has a double file extension on disk; startup_seed.py's SEED_DOCUMENTS entry intentionally matches this — do not rename without updating the seed config
- is_front_matter is only implemented for WhoHearts pages 1-13; not applied to AWaRe or Polypharmacy
- exclude_front_matter defaults to False everywhere; pipeline.py does not pass True, so front-matter exclusion is not yet active for real user queries, only in eval/smoke-test scripts
- Embedding prefix convention is load-bearing and easy to silently break: passages need "passage: ", queries need "query: ", applied only in embedder.py at embed time
