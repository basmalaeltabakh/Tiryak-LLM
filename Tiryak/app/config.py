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
GEMINI_MODEL_NAME = "gemini-3-flash-preview"

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL_NAME = "llama-3.3-70b-versatile"

# Vector DB collection name
COLLECTION_NAME = "faheem_documents"

# Retrieval settings
TOP_K_RESULTS = 5

CLINICAL_TOPIC = "Medication Safety & Drug Interaction Guidance"
RETRIEVAL_DISTANCE_BLOCK_THRESHOLD = 0.75