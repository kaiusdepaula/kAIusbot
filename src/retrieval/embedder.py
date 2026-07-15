"""Local text embedding using sentence-transformers.

Loads the model lazily (once per process) and exposes helpers that return
L2-normalized float32 vectors so that FAISS inner-product search behaves as
cosine similarity.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


@lru_cache(maxsize=1)
def _get_model():
    """Load and cache the sentence-transformers model (once per process)."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_NAME)


def embed(texts: list[str]) -> np.ndarray:
    """Embed a list of texts, returning an (N, EMBEDDING_DIM) float32 array.

    Vectors are L2-normalized so that a FAISS IndexFlatIP search over them
    is equivalent to cosine similarity search.
    """
    if not texts:
        return np.empty((0, EMBEDDING_DIM), dtype=np.float32)

    model = _get_model()
    vectors = model.encode(
        texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return vectors.astype(np.float32)


def embed_query(text: str) -> np.ndarray:
    """Embed a single query string, returning a 1D float32 array of length EMBEDDING_DIM."""
    return embed([text])[0]