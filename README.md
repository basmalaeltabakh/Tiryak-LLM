# 💊 Tiryak (ترياق) — Clinical Guideline Assistant

<p align="center">
  <b>A safety-first, evidence-grounded RAG assistant for medication safety & drug interaction guidance — built for the AI Hackathons (ITIDA × TIEC × Orange Digital Center × Creativa × iNSTANT).</b>
</p>

<p align="center">
  Core philosophy: <b>Fluent Answer ≠ Safe Answer.</b> Every response is grounded in official clinical guidelines, cited, and gated by a three-layer safety pipeline before it ever reaches the user.
</p>

---

## Overview

Tiryak answers medication safety questions — for both pharmacists and patients — using **only** official clinical guideline documents, never the LLM's own memory. It supports asking by text, voice, or by photographing a prescription or medication box.

Unlike a generic chatbot, Tiryak is built around one rule: **if the evidence isn't there, it says so instead of guessing.** Emergencies, diagnosis requests, and out-of-scope questions are refused by a templated (non-generative) response before any retrieval or generation happens — so refusals can never drift or be talked around.

---

##  Key Features

-  **Three-gate safety pipeline** — every question passes through:
  1. **Risk classification** (allowed / needs-caution / refuse) — audience-aware (patient vs. pharmacist)
  2. **Retrieval sufficiency check** — generation is hard-blocked if retrieved evidence is too weak
  3. **Post-generation grounding verification** — every claim is checked against the source text
-  **Evidence Panel** — every answer shows exactly which document, page, and excerpt it came from, with similarity scores, before the user has to trust it blindly
-  **Dual audience mode** — the same question gets a more technical answer for a pharmacist and a plainer, more cautious answer for a patient
- 🇪🇬 **Egyptian-context aware** — responds in Egyptian colloquial Arabic when asked in Arabic; looks up medications against a 24,868-record Egyptian drug database (with FDA as an international fallback)
- **Prescription & medication photo reading** — reads clearly legible medication names from a photo (never guesses illegible handwriting), looks up their identity, then routes a safety question through the same guarded pipeline
-  **Voice mode** — a custom-built unified text/voice/photo input bar; every input type goes through the identical safety pipeline, with no shortcuts
-  **Hierarchical summarization**, **entity/table extraction**, and **multi-document reasoning** across guideline sources
-  **Multi-provider LLM layer** — automatic failover between Gemini and Groq (Llama 3.3) with output sanitization for cross-lingual generation artifacts
-  **Custom evaluation layer** — faithfulness, answer relevancy, and context relevancy scoring against a labeled 18-question clinical test set
-  **Always-on knowledge base** — the core guideline document is indexed automatically at startup; no manual upload required to use the app

---

##  Architecture

```
Frontend: Streamlit (custom HTML/JS input bar — text + voice + photo, one component)
    │
    ▼
FastAPI Backend
    ├── Ingestion         → PyMuPDF, python-docx, python-pptx, EasyOCR
    ├── Chunking          → structure-aware, paragraph-grouped with overlap
    ├── Embeddings        → multilingual sentence-transformers
    ├── Vector Store      → ChromaDB (cosine similarity)
    ├── Safety Guardrails → risk classification → retrieval gate → grounding check
    ├── Grounded LLM      → Gemini ↔ Groq automatic fallback, audience & language aware
    ├── Evidence Panel    → per-answer source transparency
    ├── Drug Identity     → Egyptian drug DB (24,868 records) → FDA fallback
    ├── Prescription OCR  → Gemini multimodal image reading (no handwriting guessing)
    └── Evaluation Layer  → faithfulness, relevancy, context precision
```

---

##  Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, Python 3.13 |
| Vector Database | ChromaDB |
| Embeddings | sentence-transformers (`paraphrase-multilingual-mpnet-base-v2`) |
| LLMs | Google Gemini, Groq (Llama 3.3 70B) |
| Speech-to-Text | Groq-hosted Whisper (`whisper-large-v3`) |
| Text-to-Speech | gTTS |
| Image Understanding | Gemini multimodal (prescription/medication photo reading) |
| Drug Identity Data | [Egyptian Drug Database](https://github.com/karem505/egyptian-drug-database) (CC0), FDA openFDA API (fallback) |
| OCR (scanned PDFs) | EasyOCR (Arabic + English) |
| Frontend | Streamlit + custom JS component |
| Document Parsing | PyMuPDF, python-docx, python-pptx |

---

##  Getting Started

### Prerequisites
- Python 3.13
- A [Gemini API key](https://aistudio.google.com)
- A [Groq API key](https://console.groq.com)

### Installation

```bash
git clone https://github.com/basmalaeltabakh/Tiryak.git
cd Tiryak
python -m venv venv
venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

Create a `.env` file in the project root:
```
GEMINI_API_KEY=your_gemini_key_here
GROQ_API_KEY=your_groq_key_here
```

Place the core reference guideline PDF at:
```
data/seed_documents/polypharmacy_guide.pdf
```
*(Source: [Polypharmacy in Older People — AWTTC/NHS Wales, March 2023](https://awttc.nhs.wales/files/guidelines-and-pils/polypharmacy-in-older-people-a-guide-for-healthcare-professionals-march-2023-survey-pdf/))*

### Running the app

Run these in **two separate terminals**, both from the project root:

```bash
# Terminal 1 — Backend (also auto-indexes the seed guideline & downloads the Egyptian drug DB on first run)
uvicorn app.main:app --reload
```

```bash
# Terminal 2 — Frontend
streamlit run frontend/streamlit_app.py
```

Then visit:
- **App:** `http://localhost:8501`
- **API docs:** `http://127.0.0.1:8000/docs`

---

## 📡 API Overview

| Endpoint | Description |
|---|---|
| `POST /documents/upload` | Add an additional guideline document (optional) |
| `GET /documents/list` | List all indexed documents |
| `POST /query/ask` | Ask a question (text) — routed through the full safety pipeline |
| `POST /voice/ask` | Ask a question by voice — same safety pipeline |
| `POST /prescription/read` | Read a prescription/medication photo, identify drugs, and get safety guidance |
| `POST /summary/generate` | Generate a hierarchical summary of a guideline document |
| `POST /extract/entities` | Extract named entities |
| `POST /extract/tables` | Extract tabular data (e.g. risk classification tables) |
| `POST /evaluation/run` | Run the faithfulness/relevancy evaluation suite |

---

##  Evaluation Methodology

Tiryak includes a lightweight, RAGAS-inspired evaluation layer built directly on the production LLM providers — avoiding heavy, conflict-prone dependencies while preserving the core methodology:

- **Faithfulness** — Does the answer avoid unsupported or hallucinated claims?
- **Answer Relevancy** — Does the answer directly address the question asked?
- **Context Relevancy** — Was the retrieved context actually useful, independent of generation quality?

An 18-question labeled test set (direct / multi-chunk / ambiguous / out-of-scope / needs-caution) is included for reproducible benchmarking — see `Tiryak_Evaluation_Set_and_Demo_Script.md`.

---

##  Safety Design Principles

- The LLM **never** decides whether a drug substitution is safe, makes a diagnosis, or sets a dose — it only synthesizes and cites official guideline text.
- Refusals for emergencies/out-of-scope queries are **templated, not generated** — they cannot drift.
- Retrieval confidence has a **hard cutoff**: below threshold, the system declines rather than guessing.
- Prescription image reading **never guesses illegible handwriting** — unclear entries are flagged, not filled in.
- Every real answer carries a persistent medical disclaimer.

---

##  Roadmap (beyond hackathon scope)

- Nearest-pharmacy medication availability lookup (prototype only — not part of the core safety pipeline)
- Additional guideline documents (multi-topic knowledge base)
- Automated Precision@K benchmarking against the labeled test set
- Native mobile camera capture flow

---
