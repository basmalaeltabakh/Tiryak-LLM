# Tiryak Medication Safety Assistant

A bilingual (Arabic/English) clinical guideline assistant. Tiryak answers medication-safety and drug-interaction questions strictly by retrieving and citing passages from a set of official clinical guideline documents (WHO AWaRe, WHO HEARTS, and a Polypharmacy guide) — it does not diagnose, prescribe, or answer from general knowledge.

This document describes what is **actually implemented** in this repository, verified directly against the code and against live end-to-end test runs. Where an intended capability exists only partially, or not at all, it is labeled as such rather than implied.

---

## 1. Project Overview

Tiryak is a Retrieval-Augmented Generation (RAG) system with a FastAPI backend and a Streamlit frontend. A user (pharmacist or patient) asks a question in Arabic or English; the system retrieves the most relevant passages from an indexed set of clinical guideline PDFs, generates a grounded answer citing those passages, validates that the citations actually point at real retrieved content, and attaches a visible safety disclaimer to every response. Before generation happens at all, two independent guardrails can refuse the request outright: an LLM-based input-risk classifier, and a per-chunk retrieval-relevance filter.

## 2. Key Features

- Question answering grounded in retrieved guideline text, with inline citations that are deterministically validated against the actual retrieved sources (not just requested and trusted)
- Claim-level unsupported-claim detection that actively flags — not just displays — any part of an answer the sources don't support
- Generation language that hedges automatically when retrieval evidence is weak, calibrated to the same confidence signal shown in the UI
- Cross-lingual retrieval fix for Arabic: the query is translated to English before the vector search, since the corpus is entirely English-source text
- Prescription/medication photo reading (multimodal vision) with an "unclear — don't guess" instruction
- Voice input (speech-to-text) and spoken answers (text-to-speech)
- Document upload, summarization, and entity/table extraction for user-supplied PDFs, DOCX, and PPTX files
- Full Arabic/English UI localization with correct RTL layout
- A two-stage safety pipeline: input-risk classification before retrieval, per-chunk relevance filtering before generation
- Two complementary evaluation tools: a fast retrieval-only Precision@k harness, and a unified evaluator that computes retrieval + generation faithfulness/relevancy + citation accuracy together in one log

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
   → Input-risk classification (LLM)                  → refuse here if unsafe/out-of-scope
   → [Arabic only] Translate query to English (LLM)    → falls back to the raw Arabic text + a
                                                          wider distance cutoff if translation fails
   → Query embedding ("query: " prefix)
   → Retrieval (top-5, cosine similarity)
   → Per-chunk relevance filter (distance cutoff)       → route to "insufficient evidence" if
                                                          every retrieved chunk is filtered out
   → Retrieval confidence computed (high/medium/low)     — BEFORE generation, so it can shape it
   → Context construction (chunks → labeled prompt blocks)
   → LLM generation (citation instruction + confidence-calibrated hedging instruction)
   → Deterministic citation validation (regex-parsed citations vs. real retrieved chunk metadata)
   → Claim-level grounding check (LLM) → any unsupported claim gets appended as a visible caveat
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
| `.docx` | `python-docx` — paragraphs and table cells (tables ARE preserved here, as `" | "`-joined rows) |
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
- Single ChromaDB similarity query per question — no reranker, no hybrid/BM25 search, and no deduplication pass. (A BM25 re-ranking experiment was tried and reverted after it regressed retrieval precision; `app/rag/reranker.py` exists but is an empty, unused file.)
- **Every retrieved chunk is filtered individually before it can become context or a citation** (`app/safety/guardrails.py:filter_relevant_chunks`) — see §10. This replaced an earlier version that only checked the *average* distance across all 5 chunks, which let irrelevant chunks slip through as long as a few others happened to be close enough to drag the average down (verified directly: a query with zero relevant source content still returned "high confidence" under the old average-based check).
- **Arabic queries are translated to English before embedding** (`app/rag/language_utils.py:translate_query_to_english`). The corpus is entirely English-source PDFs, so an Arabic query is always a cross-lingual match against it, and multilingual-e5-base scores that measurably worse than a same-language query — for several real test queries, the correct source page fell out of the top-25 results entirely when queried in Arabic but ranked #1 when the same question was asked in English. Translating first turns retrieval into an English-to-English match. If all LLM providers are unavailable, translation fails gracefully and the pipeline falls back to embedding the Arabic text directly with a wider, separately-calibrated distance cutoff (`CHUNK_RELEVANCE_DISTANCE_THRESHOLD_AR`) rather than failing the request outright.
- `exclude_front_matter=True` is now passed on every retrieval call, dropping cover/TOC-style boilerplate chunks (previously only used by the evaluation script, not by the live pipeline).

`app/rag/retriever.py`

## 10. Confidence / Retrieval Guardrail

Every individually-retrieved chunk is checked against a calibrated per-chunk cosine-distance cutoff before it can be used as context or shown as a citation:

```python
def filter_relevant_chunks(chunks, distance_threshold) -> List[Dict]:
    return [c for c in chunks if c["distance"] <= distance_threshold]
```

- **English queries:** `CHUNK_RELEVANCE_DISTANCE_THRESHOLD = 0.14` — calibrated by measuring the actual distance distributions of labeled-relevant vs. labeled-irrelevant chunks returned for `scripts/eval_set.json`'s questions (relevant chunks clustered at distance ~0.10–0.18, irrelevant "noise floor" chunks at ~0.11–0.17 — the two overlap, so no cutoff is perfect, but 0.14 sits near the F1-optimal point on that labeled sample).
- **Arabic queries (translation-failure fallback only):** `CHUNK_RELEVANCE_DISTANCE_THRESHOLD_AR = 0.18` — calibrated the same way against Arabic translations of the labeled set, since Arabic queries score systematically higher-distance for identical correct content (see §9).
- **If every retrieved chunk is filtered out:** the pipeline returns an "insufficient evidence" response immediately — **the LLM is never called for generation.**
- **Retrieval confidence** (`compute_retrieval_confidence`, high/medium/low) is computed from the same calibrated threshold, and — unlike before — is computed **before** generation so it can be passed into the prompt (see §15).

This check happens in `app/rag/pipeline.py`, strictly before `generate_answer()`.

`app/safety/guardrails.py`, `app/rag/confidence.py`, `app/config.py`

## 11. Input Risk / Safety Guardrail

Independently of retrieval, every question is first classified by an LLM call into one of three risk levels, **before any retrieval happens**:

- `allowed` — a general question asking what the guidelines recommend for a condition, drug, or interaction — including severe/urgent-sounding conditions (sepsis, meningitis, stroke). Severity of the condition name is explicitly *not* a refusal trigger; only the framing of the request is.
- `needs_caution` — describes a specific real patient's situation; answered, with an extra caveat appended
- `refuse` — an emergency actually happening right now, a request to diagnose a described person, or a request to pick a specific dose/plan for a named patient — the pipeline returns a fixed refusal message and **never retrieves or generates**

The classifier prompt includes contrastive few-shot examples (e.g. *"What antibiotic should be used to treat sepsis?"* → allowed, vs. *"My patient is in septic shock right now, what do I do?"* → refuse) after live testing showed the earlier wording — "asks the assistant to decide a treatment plan" — was ambiguous enough that the Groq fallback model non-deterministically refused plain guideline-lookup questions phrased as "what is the treatment for X." Verified after the fix: 12/12 consistent `allowed` classifications across 4 previously-flaky questions, with genuine emergencies still reliably refused.

`app/safety/guardrails.py:classify_query_risk()`

## 12. LLM Layer

| | Model | Role |
|---|---|---|
| Primary | `gemini-2.5-flash` | Answer generation, risk classification, translation, grounding checks, evaluation |
| Fallback | `openai/gpt-oss-20b` (via Groq) | Same, used automatically if Gemini is exhausted or errors |

All text generation funnels through one function, `app/rag/llm_provider.py:generate_content()`, which tries Gemini first and falls back to Groq on failure. No `temperature`, `max_tokens`, or other generation parameters are set anywhere — both providers run on their default values. There is no system-role message; grounding rules are embedded directly in the user prompt.

**Operational note:** both providers have hard usage caps (Gemini free-tier daily request limit; Groq's tokens-per-day limit) that are easy to exhaust during active development/testing — when both are exhausted, every LLM-backed feature (query answering, risk classification, translation, summarization, prescription reading) returns a 503 shown as a small error banner in the UI, which can look like "the app isn't responding" rather than a quota issue. There's no queuing or backoff beyond the built-in Gemini→Groq fallback.

Prescription-photo reading is a separate multimodal call directly to Gemini (`app/advanced/image_reader.py`) — it does **not** go through `generate_content()`'s fallback, since Groq's configured model has no vision support. If Gemini is unavailable, prescription reading fails outright rather than degrading.

## 13. Grounding & Citations

The generation prompt instructs the model to cite `[Document Name, Page X]` or `[Document Name, Section: Y, Page X]` after each claim, answer only from the provided excerpts, and never phrase "the sources don't mention this" as a clinical finding of "no interaction/risk" (`app/rag/generator.py:build_context_prompt()`).

**Citations are now deterministically validated, not just requested and trusted** (`app/rag/citation_validator.py`):

- Every bracketed citation in the generated answer is parsed out via regex (looking for any `[...Page N...]` pattern, independent of field order — small/fast models don't reliably follow one exact format; observed variants included `[Source N]` shorthand, reordered fields, and citing the section title instead of the document name).
- Each parsed citation is cross-checked against the metadata of the chunks actually retrieved and used: valid only if the page number matches a real retrieved chunk **and** the citation's leading text overlaps the chunk's filename or section title.
- The result — `citation_accuracy` (valid / total), plus the list of specific invalid citations — is included in every response's `confidence` object and computed with zero extra LLM calls.
- The prompt explicitly forbids the `[Source N]` shorthand, since a citation that only makes sense by cross-referencing an internal source list isn't independently verifiable by a reader.

Live-verified: after fixing the extraction to handle real model output variance, `citation_accuracy` measured 1.0 across a small live batch of previously-flaky test questions.

`app/rag/generator.py:build_context_prompt()`, `app/rag/citation_validator.py`

## 14. Claim-Level Grounding / Unsupported-Claim Detection

`verify_answer_grounding()` (`app/rag/confidence.py`) asks the LLM to identify *specific* sentences/claims in the answer that the sources don't support, rather than a single whole-answer verdict — and, unlike before, **this is now acted on, not just displayed**: if the checker flags a claim, `app/rag/pipeline.py` appends a visible caveat to the final answer naming what isn't fully supported, in the response's own language.

Returns `{"verdict": "grounded"|"partially_grounded"|"not_grounded", "unsupported_claims": [...]}`. Both fields are included in the response's `confidence` object; `unsupported_claims` is additive and doesn't change the shape of the pre-existing `grounding_verdict` string field the frontend already reads.

## 15. Uncertainty-Calibrated Generation

Retrieval confidence (§10) is now computed **before** generation, and passed into the prompt (`app/rag/generator.py:CONFIDENCE_LANGUAGE_INSTRUCTIONS`):

- **High confidence:** no extra instruction — normal tone.
- **Medium confidence:** the model is told to hedge with phrasing like "the guideline indicates..." rather than flatly asserting facts.
- **Low confidence:** the model must open with an explicit caveat that the sources only touch the question indirectly/incompletely, before giving whatever partial information they support.

Previously, confidence signals were computed and shown in the UI but never fed back into how the answer itself was worded.

## 16. Arabic/English Support

- **Frontend:** a centralized translation dictionary (`TRANSLATIONS` / `t()` in `frontend/streamlit_app.py`) covers every page, label, and message; the sidebar mirrors correctly in Arabic (right-anchored, icon/label order reversed).
- **Backend:** `app/rag/language_utils.py:detect_language()` detects Arabic by checking for Arabic-range Unicode characters in the question. The generation prompt then instructs the model to answer in Egyptian colloquial Arabic (not formal MSA) or English accordingly.
- **Retrieval:** Arabic queries are translated to English before the vector search (§9) — the single highest-impact fix for Arabic answer quality, since the corpus itself has no Arabic source text.
- **Query/generation separation:** the frontend can send a `retrieval_query` separate from the (possibly patient-context-enriched) `question` sent for generation — `app/api/routes_query.py`, `app/rag/pipeline.py`. This exists because the frontend prepends patient-context and language-directive boilerplate (e.g. `"[Patient context — ...]"`) to the question for richer generation, and embedding that boilerplate alongside the real question measurably degraded retrieval (verified: pulled in closer-but-still-irrelevant chunks for an unrelated hypertension-context test). The frontend now sends the clean original text as `retrieval_query` while `question` still carries full context to the LLM.
- Voice input/output and OCR both support Arabic alongside English.

## 17. Evaluation

Two complementary tools, covering what used to be two disconnected pieces:

**Retrieval-only Precision@k** (`scripts/run_eval.py`) — fast, no generation cost, runs against **20 hand-labeled questions** (`scripts/eval_set.json`: 6 direct, 5 multi-chunk, 4 ambiguous, 3 out-of-scope, 2 needs-caution). A retrieved chunk counts as relevant only if its page number is in the question's labeled `expected_source_pages` and its filename matches the expected document.

**Unified evaluation** (`scripts/run_full_eval.py`, new) — computes retrieval Precision@k, generation faithfulness/answer-relevancy/context-relevancy (LLM-judged, via `app/evaluation/evaluator.py`), *and* citation accuracy together against the same labeled questions, saving one consolidated log (`scripts/full_eval_results.json`). Costs ~4 LLM calls per question, so it defaults to a small subset (`--limit`, default 6; pass `--limit 0` for the full labeled set) rather than always burning the full budget. Resilient to a mid-run provider outage — a failed question is logged and skipped rather than losing every result collected so far.

**Current results** (`run_eval.py`, reproducible by running the command below):

| Metric | Value |
|---|---|
| Mean P@3 | **0.4314** |
| Mean P@5 | **0.3529** |
| Questions scored | 17 |
| Out-of-scope questions skipped | 3 |

This retrieval metric predates the per-chunk relevance filter and Arabic-translation changes described above — it measures raw retriever ranking quality, not what the live pipeline actually returns to a user after filtering.

## 18. Engineering Highlights

A few things worth calling out that separate this from a minimal RAG demo:

- **Every relevance and confidence threshold is empirically calibrated, not guessed** — measured directly against labeled data (`scripts/eval_set.json`), separately for English and Arabic, since the two turned out to need different cutoffs on this embedding model.
- **Citations are independently verified, not just requested.** The generation prompt asks for a citation format; a deterministic validator then cross-checks every single one against the metadata of the chunks that were actually retrieved, with zero added LLM cost.
- **The system catches its own model's formatting drift.** Live testing surfaced three different ways the fallback model varied its citation style — the validator was hardened against all three rather than papering over the variance with prompt tweaks alone.
- **Confidence isn't just displayed — it changes behavior.** Retrieval confidence is computed *before* generation and shapes how hedged the answer's language is; claim-level grounding checks actively append a caveat to the answer when something isn't supported, instead of only showing a score.
- **Cross-lingual retrieval was diagnosed and fixed at the root cause**, not patched around — Arabic queries are translated to English before the vector search, since the entire corpus is English-source text, with a safe fallback if translation is ever unavailable.

## 19. Testing & Evaluation Commands

Run all commands from the repository root (`Tiryak/`), with the virtual environment active.

```bash
# Retrieval Precision@k against the labeled 20-question set (fast, retrieval only)
python -m scripts.run_eval

# Unified evaluation: retrieval + generation faithfulness/relevancy + citation accuracy,
# saved to one log. Costs real LLM calls — defaults to 6 questions.
python -m scripts.run_full_eval --limit 6
python -m scripts.run_full_eval --limit 0   # full labeled set

# Manual retrieval sanity check (5 hardcoded queries, prints top-3 + similarity)
python -m scripts.retrieval_smoke_test

# Chunking diagnostics for the 3 seed documents (chunk counts, dropped/oversized chunks)
python -m scripts.ingestion_report

# LLM-judged generation evaluation (faithfulness / answer relevancy / context relevancy)
# — requires the backend running; superseded by run_full_eval.py for most purposes
curl -X POST http://127.0.0.1:8000/evaluation/run \
  -H "Content-Type: application/json" \
  -d '{"document_ids": [], "test_questions": ["What is the first-line antibiotic for pharyngitis?"]}'
```

## 20. Project Structure

```
Tiryak/
├── app/
│   ├── main.py              # FastAPI app + router registration
│   ├── config.py            # Models, chunking, and threshold configuration
│   ├── startup_seed.py      # Auto-indexes the 3 seed guideline PDFs on startup
│   ├── api/                 # Route handlers: documents, query, summary, extract, voice, evaluation, prescription
│   ├── rag/                 # pipeline, retriever, generator, confidence, citation_validator, llm_provider, language_utils
│   ├── ingestion/           # parsers, chunker, ocr, aware_parser, hearts_parser
│   ├── embeddings/          # embedder, vector_store
│   ├── safety/               # guardrails (input-risk + per-chunk relevance filter)
│   ├── evaluation/          # evaluator (LLM-judged faithfulness / relevancy)
│   └── advanced/            # drug lookup, document summarizer, entity extraction, voice, image reading
├── frontend/
│   ├── streamlit_app.py     # Streamlit UI (English/Arabic)
│   └── voice_input_component/  # Custom Streamlit component: text/voice/image input bar
├── scripts/
│   ├── run_eval.py              # Precision@k evaluation (retrieval only)
│   ├── run_full_eval.py         # Unified evaluation: retrieval + generation + citation accuracy
│   ├── retrieval_smoke_test.py
│   ├── ingestion_report.py
│   ├── eval_set.json             # 20 labeled evaluation questions
│   ├── eval_results.json         # Last saved run_eval.py output
│   ├── full_eval_results.json    # Last saved run_full_eval.py output
│   └── refusal_demo_case.json    # One rehearsed, verified refusal example for demos
├── data/
│   ├── seed_documents/       # The 3 seeded clinical guideline PDFs
│   └── chroma_db/            # Persistent vector store
├── tests/                    # Currently empty
├── requirements.txt
└── .env                       # GEMINI_API_KEY, GROQ_API_KEY
```

## 21. Setup & Installation

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

## 22. How to Run

```bash
# Terminal 1 — backend (from the Tiryak/ directory)
uvicorn app.main:app --reload
# Seeds the 3 guideline PDFs into ChromaDB automatically on first startup.
# API docs available at http://127.0.0.1:8000/docs

# Terminal 2 — frontend
streamlit run frontend/streamlit_app.py
```

## 23. Example RAG Flow

A real, traced question through the running system (`user_type="pharmacist"`):

**Question:** *"What is the first-line antibiotic for pharyngitis?"*

1. **Input-risk check:** classified `allowed` — general guideline question.
2. **Retrieval:** top 5 chunks returned from the WHO AWaRe document; all pass the 0.14 per-chunk relevance filter.
3. **Confidence:** computed before generation as `medium`/`high` depending on the exact run — passed into the prompt to calibrate hedging language.
4. **Generation:** amoxicillin / phenoxymethylpenicillin dosing, citing the real document name, section, and page for every claim.
5. **Citation validation:** every inline citation cross-checked against the actual retrieved chunks — `citation_accuracy: 1.0` in this run.
6. **Grounding check:** no unsupported claims found — no caveat appended.
7. **Final answer:** dosing information with inline citations, followed automatically by the standard safety disclaimer.

For comparison, **a real Arabic query that previously failed**: *"كيف يتم تقليل جرعة البنزوديازيبينات بأمان؟"* ("How is the benzodiazepine dose safely tapered?"). Before the Arabic-translation fix, the correct source page (Polypharmacy guide, p.17) ranked #7 in retrieval — outside the top-5, so the system returned "insufficient evidence" despite the answer existing in the corpus. After the fix: the query is translated to *"How to safely reduce the dose of benzodiazepines?"*, the correct page now ranks #1 at a comfortably-passing distance, and the system returns a correctly-cited answer in Egyptian Arabic.

And the other side: *"I'm having severe chest pain right now, what should I do?"* is refused at step 1 — retrieval and generation never run — even though retrieval alone would confidently return a chunk for it if reached. This exact case is saved as a rehearsed demo example in `scripts/refusal_demo_case.json`.

## 24. Responsible AI / Clinical Safety

- Every non-refused answer has this disclaimer appended automatically: *"This information is provided for reference based on official guidelines. It supports — but does not replace — professional medical judgment. Always verify against the full clinical picture, and consult a pharmacist, physician, or poison control center for emergencies."* (`app/safety/guardrails.py:SAFETY_DISCLAIMER`)
- Emergencies, diagnosis requests, and specific dosing decisions for a named patient are refused before retrieval, via the input-risk classifier (§11) — calibrated with contrastive examples so it doesn't over-refuse plain guideline-lookup questions about severe-sounding conditions.
- Questions with no individually-relevant retrieved chunk are refused before generation, via the per-chunk relevance filter (§10) — replacing an earlier average-based check that could be fooled by several mediocre-but-irrelevant chunks.
- The generation prompt explicitly forbids treating "the sources don't mention this" as a clinical finding that no interaction/risk exists.
- Citations are deterministically validated against real retrieved content, and specific unsupported claims are surfaced as a visible caveat rather than only logged internally.
- Refusal and insufficient-evidence responses are fixed template text, not LLM-generated — they cannot be inadvertently softened by prompt drift.
- Patient-audience questions receive additional conservative handling: any request that reads as an instruction to start/stop/change medication is classified at least `needs_caution`.

---

## Implementation Status

### Implemented
- Multilingual (Arabic/English) RAG pipeline: parsing → heading-aware chunking → embedding → ChromaDB retrieval → grounded generation
- Per-chunk relevance filter that blocks generation before the LLM is called, calibrated separately for English (0.14) and Arabic (0.18) query distance distributions
- Cross-lingual retrieval fix: Arabic queries translated to English before embedding, with graceful fallback if translation is unavailable
- LLM-based input-risk classifier with contrastive examples, verified not to over-refuse plain guideline questions about severe conditions
- Deterministic citation validation: every inline citation cross-checked against real retrieved chunk metadata, zero extra LLM cost
- Claim-level unsupported-claim detection that actively appends a caveat to the answer, not just a displayed verdict
- Uncertainty-calibrated generation: retrieval confidence computed before generation and used to adjust hedging language
- Deterministic `sources`/`evidence_panel` citation metadata, built directly from retrieved chunks
- Automatic multi-provider LLM fallback (Gemini → Groq) for every text-generation call except prescription-image reading
- Two evaluation tools: fast retrieval-only Precision@k (P@3 = 0.4314, P@5 = 0.3529), and a unified retrieval+generation+citation-accuracy evaluator that saves one consolidated log
- Full Arabic/English UI localization with correct RTL behavior
- Visible, always-appended clinical safety disclaimer
- One rehearsed, live-verified refusal test case saved for demos (`scripts/refusal_demo_case.json`)

---

## Team

- **[Basmala Saeed](https://github.com/basmalaeltabakh)**
- **[Tahany Emad](https://github.com/Tahanyemad16)**
- **[Merhan Medhat](https://github.com/merhanmedhat2006-max)**

