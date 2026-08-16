from sentence_transformers import SentenceTransformer
from typing import List
from app.config import EMBEDDING_MODEL_NAME

_model = None


def get_embedding_model():
    """
    Lazy-loads the multilingual embedding model.
    Loaded once and reused across calls since loading it is expensive.
    """
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _model


def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Converts a list of text strings into a list of embedding vectors.
    """
    model = get_embedding_model()
    embeddings = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
    return embeddings.tolist()


def embed_single_text(text: str) -> List[float]:
    """
    Convenience function for embedding a single string (e.g., a user query).
    """
    return embed_texts([text])[0]