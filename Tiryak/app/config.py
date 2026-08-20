import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
CHROMA_DIR = DATA_DIR / "chroma_db"

# Ensure directories exist
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
CHROMA_DIR.mkdir(parents=True, exist_ok=True)

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Embedding model
# multilingual-e5-base: 512-token context (vs. 128 for the previous mpnet
# model), 768-dim, strong Arabic/English performance. Requires "query: " /
# "passage: " input prefixes (applied in app/embeddings/embedder.py, not
# stored in chunk text) — see that module for why both are needed.
EMBEDDING_MODEL_NAME = "intfloat/multilingual-e5-base"

# Chunking settings — token-based (measured with the embedding model's own
# tokenizer, see app/embeddings/embedder.py:count_tokens), shared by all
# three document chunkers (app/ingestion/chunker.py, hearts_parser.py,
# aware_parser.py) so every document is sized against the same real budget.
# multilingual-e5-base supports up to 512 tokens; targeting well under that
# leaves headroom for the model's own special tokens and keeps each chunk
# focused on one coherent recommendation rather than several.
CHUNK_TARGET_TOKENS = 400   # greedy packing stops once a chunk would exceed this
CHUNK_MAX_TOKENS = 450      # hard ceiling — a single oversized section gets split at this size
CHUNK_OVERLAP_TOKENS = 40   # ~10% of CHUNK_TARGET_TOKENS, used when a section must be split
CHUNK_DROP_TOKENS = 80      # chunks smaller than this are extraction noise, dropped before storage

# Gemini model
GEMINI_MODEL_NAME = "gemini-2.5-flash"

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL_NAME = "openai/gpt-oss-20b"

# Vector DB collection name
COLLECTION_NAME = "faheem_documents"

# Retrieval settings
TOP_K_RESULTS = 5

CLINICAL_TOPIC = "Medication Safety & Drug Interaction Guidance"

# Per-chunk cosine-distance cutoff below which a retrieved chunk is treated as
# actually relevant to the query (app/safety/guardrails.py:filter_relevant_chunks).
# Calibrated against scripts/eval_set.json's labeled relevant/irrelevant chunks
# for multilingual-e5-base on this corpus: relevant chunks cluster at
# distance ~0.10-0.18 (mean 0.129), irrelevant "noise floor" chunks returned by
# any query also cluster at ~0.11-0.17 (mean 0.137) — the two overlap heavily,
# so no threshold is perfect, but 0.14 is close to the F1-optimal cut (0.136)
# on that labeled set. Re-run the calibration in scripts/run_eval.py's style
# whenever the embedding model or corpus changes materially.
CHUNK_RELEVANCE_DISTANCE_THRESHOLD = 0.14

# Same cutoff, but for Arabic queries. The corpus is entirely English-source
# PDFs, so an Arabic query is always a CROSS-LINGUAL match against English
# text — multilingual-e5-base scores that systematically higher-distance
# (worse) than a same-language English query for the exact same content, even
# when it's the correct answer. Measured directly (8 Arabic translations of
# labeled eval questions): relevant top hits landed at distance ~0.17-0.22,
# 0.06-0.10 higher than their English equivalents for the identical source
# page. Reusing the English 0.14 cutoff for Arabic queries was silently
# routing most legitimately-answerable Arabic questions to "insufficient
# evidence". F1-optimal on that small labeled sample was ~0.177; 0.18 is used
# with a little extra headroom given the sample size. Re-calibrate with a
# larger labeled Arabic set if one gets built.
CHUNK_RELEVANCE_DISTANCE_THRESHOLD_AR = 0.18