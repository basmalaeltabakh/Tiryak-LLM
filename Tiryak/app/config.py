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
EMBEDDING_MODEL_NAME = "paraphrase-multilingual-mpnet-base-v2"

# Chunking settings
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

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