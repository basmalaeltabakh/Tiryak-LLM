# Tiryak

A bilingual (Arabic/English) clinical guideline assistant. Tiryak answers medication-safety and drug-interaction questions strictly by retrieving and citing passages from a set of official clinical guideline documents (WHO AWaRe, WHO HEARTS, and a Polypharmacy guide) — it does not diagnose, prescribe, or answer from general knowledge.

This document describes what is **actually implemented** in this repository, verified directly against the code. Where an intended capability exists only partially, or not at all, it is labeled as such rather than implied.

---

## 1. Project Overview

Tiryak is a Retrieval-Augmented Generation (RAG) system with a FastAPI backend and a Streamlit frontend. A user (pharmacist or patient) asks a question in Arabic or English; the system retrieves the most relevant passages from an indexed set of clinical guideline PDFs, generates a grounded answer citing those passages, and attaches a visible safety disclaimer to every response. Before generation happens at all, two independent guardrails can refuse the request outright: an LLM-based input-risk classifier, and a retrieval-confidence threshold.

## 2. Key Features

- Question answering grounded in retrieved guideline text, with inline citations
- Prescription/medication photo reading (multimodal vision) with an "unclear — don't guess" instruction
- Voice input (speech-to-text) and spoken answers (text-to-speech)
- Document upload, summarization, and entity/table extraction for user-supplied PDFs, DOCX, and PPTX files
- Full Arabic/English UI localization with correct RTL layout
- A two-stage safety pipeline: input-risk classification before retrieval, retrieval-confidence gating before generation
- A reproducible Precision@k retrieval evaluation harness against a hand-labeled question set

## 3. System Architecture

| Layer | Technology |
|---|---|
| Frontend | Streamlit (single app, `frontend/streamlit_app.py`) |
| Backend | FastAPI + Uvicorn |
| Vector store | ChromaDB (persistent, on disk) |
| Relational database | **None** — a SQLAlchemy scaffold exists (`db/`) but both files are empty and unused |
| LLM | Google Gemini (primary), Groq (fallback) |
| Embeddings | `sentence-transformers` (multilingual-e5-base) |

The frontend talks to the backend exclusively over HTTP (`http://127.0.0.1:8000` by default). All retrieval, generation, and safety logic lives in the backend; the frontend only renders what the backend returns.

## 4. End-to-End RAG Pipeline

```
Document (PDF/DOCX/PPTX)
   → Parsing (per-file-type; OCR fallback for scanned PDFs)
   → Chunking (heading-aware, token-budgeted)
   → Embedding (multilingual-e5-base, "passage: " prefix)
   → ChromaDB (persistent, cosine distance)

User question
   → Input-risk classification (LLM)              → refuse here if unsafe/out-of-scope
   → Query embedding ("query: " prefix)
   → Retrieval (top-5, cosine similarity)
   → Retrieval-confidence gate (mean distance)     → refuse here if evidence is too weak
   → Context construction (chunks → labeled prompt blocks)
   → LLM generation (with inline citation instruction)
   → Deterministic sources/evidence list (built from retrieved-chunk metadata)
   → Disclaimer appended
   → Final answer
```

Orchestrated end-to-end in `app/rag/pipeline.py:answer_question_safely()`.

## 5. Document Ingestion & Parsing

| File type | Parser |
|---|---|
| `.pdf` | PyMuPDF (`fitz`), page-by-page text extraction |
| `.pdf` (scanned) | Auto-detected (avg. <20 extractable characters/page) and OCR'd with EasyOCR (Arabic + English) |
| `.docx` | `python-docx` — paragraphs and table cells |
| `.pptx` | `python-pptx` — one "page" per slide |

Three seed documents (WHO AWaRe, WHO HEARTS, Polypharmacy guide) are ingested automatically on backend startup (`app/startup_seed.py`) using two dedicated layout parsers for the WHO documents' infographic-style pages, and the generic parser below for everything else, including user uploads.

`app/ingestion/parsers.py`, `app/ingestion/ocr.py`, `app/ingestion/aware_parser.py`, `app/ingestion/hearts_parser.py`

## 6. Chunking Strategy

The generic chunker (`app/ingestion/chunker.py`) is **heading-aware and token-budgeted**, not fixed-size:

1. Strips repeated running headers/footers (lines appearing on >50% of pages) and table-of-contents pages.
2. Splits on numbered section headings (e.g. `6.1 Antihypertensives`), building a hierarchical breadcrumb so nested subsections stay attributed to their parent.
3. Greedily packs consecutive sections into a chunk without ever splitting a section across a chunk boundary — a section is only force-split if it alone exceeds the max size.

| Parameter | Value | Meaning |
|---|---|---|
| `CHUNK_TARGET_TOKENS` | 400 | Greedy packing stops once a chunk would exceed this |
| `CHUNK_MAX_TOKENS` | 450 | Hard ceiling — an oversized section is force-split at this size |
| `CHUNK_OVERLAP_TOKENS` | 40 | Overlap applied only when a section must be force-split |
| `CHUNK_DROP_TOKENS` | 80 | Chunks smaller than this are treated as extraction noise and dropped |

Token counts are measured with the **embedding model's own tokenizer** (not a word-count estimate), so a chunk is never silently truncated at embed time. Configured in `app/config.py`.

## 7. Embedding Model

- **Model:** `intfloat/multilingual-e5-base`
- **Library:** `sentence-transformers`
- **Dimensions:** 768
- **Context window:** 512 tokens
- Requires input to be prefixed with `"query: "` (search queries) or `"passage: "` (stored chunks) — applied only at embed time in `app/embeddings/embedder.py`; the stored/displayed chunk text stays clean.

## 8. Vector Database

- **Technology:** ChromaDB (`PersistentClient`)
- **Distance metric:** cosine (`hnsw:space: cosine`, set explicitly — Chroma's default is L2)
- **Storage:** persistent, on disk at `data/chroma_db/`
- The collection tags itself with the embedding model it was built with; if the configured model ever changes, the collection is automatically dropped and rebuilt rather than silently mixing incompatible vector spaces.
- Metadata filtering by `document_id` is supported (used for "search within these documents" in the UI).

`app/embeddings/vector_store.py`

## 9. Retrieval

- **Top-K:** 5 (`TOP_K_RESULTS` in `app/config.py`)
- Single ChromaDB similarity query per question — no reranking, no hybrid/BM25 search, and no deduplication pass. (A BM25 re-ranking experiment was tried and reverted after it regressed retrieval precision; `app/rag/reranker.py` exists but is an empty, unused file.)

`app/rag/retriever.py`

## 10. Confidence / Retrieval Guardrail

Before generation is allowed, `check_retrieval_sufficiency()` computes the **mean cosine distance across the top-5 retrieved chunks** and compares it to a threshold:

```python
def check_retrieval_sufficiency(chunks, distance_threshold: float = 0.75) -> bool:
    avg_distance = sum(c["distance"] for c in chunks) / len(chunks)
    return avg_distance <= distance_threshold
```

- **If mean distance ≤ 0.75:** generation proceeds normally.
- **If mean distance > 0.75 (or no chunks retrieved at all):** the pipeline returns an "insufficient evidence" response immediately — **the LLM is never called for generation.**

This check happens in `app/rag/pipeline.py`, strictly before `generate_answer()`. It measures the *average* similarity across all returned chunks, not just the closest one.

`app/safety/guardrails.py`, `app/rag/pipeline.py`

## 11. Input Risk / Safety Guardrail

Independently of retrieval, every question is first classified by an LLM call into one of three risk levels, **before any retrieval happens**:

- `allowed` — general guideline question, answered normally
- `needs_caution` — describes a specific personal scenario; answered, with an extra caveat appended
- `refuse` — a medical emergency, a request for diagnosis/dosing decisions, or out-of-scope — the pipeline returns a fixed refusal message and **never retrieves or generates**

This is the guardrail that actually protects against emergency/out-of-scope questions — retrieval alone can still return a superficially similar-looking chunk for such questions, but the risk classifier intercepts them first.

`app/safety/guardrails.py:classify_query_risk()`

## 12. LLM Layer

| | Model | Role |
|---|---|---|
| Primary | `gemini-3.6-flash` | Answer generation, risk classification, grounding checks, evaluation |
| Fallback | `openai/gpt-oss-20b` (via Groq) | Same, used automatically if Gemini is exhausted or errors |

All text generation funnels through one function, `app/rag/llm_provider.py:generate_content()`, which tries Gemini first and falls back to Groq on failure. No `temperature`, `max_tokens`, or other generation parameters are set anywhere — both providers run on their default values. There is no system-role message; grounding rules are embedded directly in the user prompt.

Prescription-photo reading is a separate multimodal call to the same Gemini model with image input (`app/advanced/image_reader.py`).

## 13. Grounding & Citations

The generation prompt instructs the model to cite `[Document Name, Page X]` after each claim, and to answer only from the provided excerpts (`app/rag/generator.py:build_context_prompt()`). Two distinct things are both called "citations" here:

- **Inline text citations** — written by the LLM as free text. Nothing parses these back out and checks them against real chunk metadata.
- **The `sources` / `evidence_panel` lists** shown in the UI — built deterministically in code, directly from the metadata of the chunks that were actually retrieved (filename, page, similarity distance, section title). These are guaranteed accurate to what was retrieved.

There is currently no automated check that the model's own inline citations match the deterministic source list (see [Limitations](#16-current-limitations--known-gaps)).

## 14. Arabic/English Support

- **Frontend:** a centralized translation dictionary (`TRANSLATIONS` / `t()` in `frontend/streamlit_app.py`) covers every page, label, and message; the sidebar mirrors correctly in Arabic (right-anchored, icon/label order reversed).
- **Backend:** `app/rag/language_utils.py:detect_language()` detects Arabic by checking for Arabic-range Unicode characters in the question. The generation prompt then instructs the model to answer in Egyptian colloquial Arabic (not formal MSA) or English accordingly.
- Voice input/output and OCR both support Arabic alongside English.

## 15. Evaluation

A deterministic, reproducible Precision@k harness (`scripts/run_eval.py`) runs the retriever — not the full pipeline — against **20 hand-labeled questions** (`scripts/eval_set.json`: 6 direct, 5 multi-chunk, 4 ambiguous, 3 out-of-scope, 2 needs-caution).

**What it measures:** for each question, a retrieved chunk counts as *relevant* only if its page number is in that question's labeled `expected_source_pages` **and** its filename matches the expected document. Precision@k is then `relevant chunks in top-k / k`, averaged across all scored (non-out-of-scope) questions.

**Current results** (reproducible by running the command below):

| Metric | Value |
|---|---|
| Mean P@3 | **0.4314** |
| Mean P@5 | **0.3529** |
| Questions scored | 17 |
| Out-of-scope questions skipped | 3 |

This metric evaluates **retrieval quality only** — it does not touch generation, citations, or faithfulness.

## 16. Current Limitations / Known Gaps

These are real, verified gaps — not omissions:

- **Claim-level unsupported-claim detection is not implemented.** `app/rag/confidence.py:verify_answer_grounding()` asks the LLM to rate the *whole answer* as grounded/partially/not-grounded in a single call — it does not split the answer into individual claims or match them against retrieved text, and its result is only displayed to the user, never used to gate or flag the answer.
- **Citation accuracy is not scored.** No code validates that the model's inline citations reference a real document, the correct page/section, and text that actually supports the claim.
- **Faithfulness does not use a claims-supported/total-claims formula.** `app/evaluation/evaluator.py:evaluate_faithfulness()` returns a single 0.0–1.0 LLM judgment instead. It is reachable via `POST /evaluation/run` but is never called by the frontend, and no run has been logged.
- **No unified evaluation suite.** Retrieval evaluation (`run_eval.py`) and generation evaluation (`/evaluation/run`) are two separate, disconnected tools; neither includes citation accuracy, and nothing runs all three together against the labeled set.
- **Uncertainty language is not calibrated in the generated answer.** Confidence signals (`retrieval_confidence`, `grounding_verdict`) are computed and shown in the UI, but the generation prompt does not change its phrasing based on evidence strength.
- **`ragas` (listed in `requirements.txt`) is unused** — not installed in the active environment, and `app/evaluation/ragas_eval.py` is an empty file.
- **No automated test suite.** `tests/test_ingestion.py` is empty; there are diagnostic scripts (see below) but no assertions-based tests or CI.

## 17. Testing & Evaluation Commands

Run all commands from the repository root (`Tiryak/`), with the virtual environment active.

```bash
# Retrieval Precision@k against the labeled 20-question set
python -m scripts.run_eval

# Manual retrieval sanity check (5 hardcoded queries, prints top-3 + similarity)
python -m scripts.retrieval_smoke_test

# Chunking diagnostics for the 3 seed documents (chunk counts, dropped/oversized chunks)
python -m scripts.ingestion_report

# LLM-judged generation evaluation (faithfulness / answer relevancy / context relevancy)
# — requires the backend running; not called by the frontend
curl -X POST http://127.0.0.1:8000/evaluation/run \
  -H "Content-Type: application/json" \
  -d '{"document_ids": [], "test_questions": ["What is the first-line antibiotic for pharyngitis?"]}'
```

## 18. Project Structure

```
Tiryak/
├── app/
│   ├── main.py              # FastAPI app + router registration
│   ├── config.py            # Models, chunking, and threshold configuration
│   ├── startup_seed.py      # Auto-indexes the 3 seed guideline PDFs on startup
│   ├── api/                 # Route handlers: documents, query, summary, extract, voice, evaluation, prescription
│   ├── rag/                 # pipeline, retriever, generator, confidence, llm_provider, language_utils
│   ├── ingestion/           # parsers, chunker, ocr, aware_parser, hearts_parser
│   ├── embeddings/          # embedder, vector_store
│   ├── safety/              # guardrails (input-risk + retrieval-confidence)
│   ├── evaluation/          # evaluator (LLM-judged faithfulness / relevancy)
│   └── advanced/            # drug lookup, document summarizer, entity extraction, voice, image reading
├── frontend/
│   └── streamlit_app.py     # Streamlit UI (English/Arabic)
├── scripts/
│   ├── run_eval.py              # Precision@k evaluation
│   ├── retrieval_smoke_test.py
│   ├── ingestion_report.py
│   ├── eval_set.json             # 20 labeled evaluation questions
│   └── eval_results.json         # Last saved run output
├── data/
│   ├── seed_documents/       # The 3 seeded clinical guideline PDFs
│   └── chroma_db/            # Persistent vector store
├── tests/                    # Currently empty
├── requirements.txt
└── .env                      # GEMINI_API_KEY, GROQ_API_KEY
```

## 19. Setup & Installation

```bash
# 1. Clone and enter the project
cd Tiryak

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure API keys
cat > .env << EOF
GEMINI_API_KEY=your_gemini_key_here
GROQ_API_KEY=your_groq_key_here
EOF
```

## 20. How to Run

```bash
# Terminal 1 — backend (from the Tiryak/ directory)
uvicorn app.main:app --reload
# Seeds the 3 guideline PDFs into ChromaDB automatically on first startup.
# API docs available at http://127.0.0.1:8000/docs

# Terminal 2 — frontend
streamlit run frontend/streamlit_app.py
```

## 21. Example RAG Flow

A real, traced question through the running system (`user_type="pharmacist"`):

**Question:** *"What is the first-line antibiotic for pharyngitis?"*

1. **Input-risk check:** classified `allowed` — general guideline question.
2. **Retrieval:** top 5 chunks returned, all from the WHO AWaRe document, cosine distances 0.117–0.158 (similarity 0.84–0.88), pages 14, 16, 16, 14, 91.
3. **Confidence gate:** mean distance 0.135 ≤ 0.75 → passes, generation proceeds.
4. **Generation:** answered by `gemini`, citing "[WHO AWaRe Antibiotic Book…, Page 14]" and "Page 16" inline — both match the pages actually retrieved.
5. **Confidence report:** `retrieval_confidence: "high"`, `grounding_verdict: "grounded"`.
6. **Final answer:** amoxicillin / phenoxymethylpenicillin dosing with inline citations, followed automatically by the standard safety disclaimer.

For comparison, the question *"I'm having severe chest pain right now, what should I do?"* is refused at step 1 — retrieval and generation never run — even though retrieval alone would have confidently returned a chunk for it (similarity 0.82) if it had been reached.

## 22. Responsible AI / Clinical Safety

- Every non-refused answer has this disclaimer appended automatically: *"This information is provided for reference based on official guidelines. It supports — but does not replace — professional medical judgment. Always verify against the full clinical picture, and consult a pharmacist, physician, or poison control center for emergencies."* (`app/safety/guardrails.py:SAFETY_DISCLAIMER`)
- Emergencies, diagnosis requests, and specific dosing decisions are refused before retrieval, via the input-risk classifier (Section 11).
- Questions unsupported by retrieved evidence are refused before generation, via the confidence gate (Section 10).
- Refusal and insufficient-evidence responses are fixed template text, not LLM-generated — they cannot be inadvertently softened by prompt drift.
- Patient-audience questions receive additional conservative handling: any request that reads as an instruction to start/stop/change medication is classified at least `needs_caution`.
- **Not yet implemented:** automated regression testing of refusal behavior, and post-hoc claim-level validation of generated answers (see Section 16).

---

## Implementation Status

###  Implemented
- Multilingual (Arabic/English) RAG pipeline: parsing → heading-aware chunking → embedding → ChromaDB retrieval → grounded generation
- Retrieval-confidence guardrail that blocks generation before the LLM is called (mean distance ≤ 0.75)
- LLM-based input-risk classifier that refuses before retrieval (emergency/diagnosis/out-of-scope)
- Deterministic `sources` / `evidence_panel` citation metadata, built directly from retrieved chunks
- Automatic multi-provider LLM fallback (Gemini → Groq)
- Reproducible Precision@k retrieval evaluation against a 20-question labeled set (P@3 = 0.4314, P@5 = 0.3529)
- Full Arabic/English UI localization with correct RTL behavior
- Visible, always-appended clinical safety disclaimer

###  Implemented but Incomplete
- Whole-answer LLM grounding check exists but is display-only, not enforced, and not claim-level
- Faithfulness metric exists but as a single LLM judgment, not the claims-supported/total-claims formula, and has no logged run
- Confidence signals are computed and shown but don't calibrate the generated answer's wording
- Generation-evaluation endpoint (`/evaluation/run`) exists but is unreachable from the UI and has no saved results

###  Not Yet Implemented
- Claim-level unsupported-claim detection (split → match → flag)
- Citation accuracy scoring
- A unified evaluation suite combining retrieval, generation, and citation scoring in one pass
- Automated tests (unit, integration, or safety-regression)
- Reranking / hybrid search (tried, reverted — currently pure vector similarity only)
