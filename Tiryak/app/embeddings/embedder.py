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


def _encode_with_prefix(texts: List[str], prefix: str) -> List[List[float]]:
    model = get_embedding_model()
    prefixed = [f"{prefix}{t}" for t in texts]
    embeddings = model.encode(prefixed, show_progress_bar=False, convert_to_numpy=True)
    return embeddings.tolist()


def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Converts a list of chunk/passage strings into embedding vectors, for
    storage in the vector store.

    multilingual-e5-base requires every input to be prefixed with "query: "
    or "passage: " (per the model's own documentation: omitting this causes
    a measurable performance degradation, for both queries AND passages —
    not just queries). The prefix is applied here only, right before
    encoding; the text stored in Chroma / shown in citations stays clean.
    """
    return _encode_with_prefix(texts, "passage: ")


def embed_single_text(text: str) -> List[float]:
    """
    Embeds a single query string for similarity search (see embed_texts for
    why the "query: " prefix matters). Not used for passages — the only
    caller is the retriever.
    """
    return _encode_with_prefix([text], "query: ")[0]


def get_tokenizer():
    """
    Exposes the embedding model's own HuggingFace tokenizer, so chunk sizing
    (app/ingestion/chunker.py) measures against the exact same tokenization
    the model will use at embed time, instead of a words-vs-tokens estimate.
    """
    return get_embedding_model().tokenizer


def count_tokens(text: str) -> int:
    """Token count as the embedding model's tokenizer will actually see it."""
    return len(get_tokenizer().encode(text, add_special_tokens=False))