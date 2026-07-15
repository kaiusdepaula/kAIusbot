"""In-memory FAISS index built from the DuckDB chunk store.

The index is built lazily on first use and cached for the process lifetime.
Since embeddings are L2-normalized (see `embedder.py`), `IndexFlatIP` (inner
product) search is equivalent to cosine similarity search.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb
import faiss
import numpy as np

from src.retrieval import store
from src.retrieval.embedder import EMBEDDING_DIM

_CACHE: "FaissIndex | None" = None


@dataclass
class FaissIndex:
    index: "faiss.IndexFlatIP"
    id_list: list[int]


def build_index(conn: duckdb.DuckDBPyConnection) -> FaissIndex | None:
    """Build a FAISS index from all embeddings currently in the DuckDB store.

    Returns None if the store is empty (no ingestion has been run yet).
    """
    ids, vectors = store.fetch_all(conn)
    if not ids:
        return None

    index = faiss.IndexFlatIP(EMBEDDING_DIM)
    index.add(vectors)
    return FaissIndex(index=index, id_list=ids)


def get_cached_index(conn: duckdb.DuckDBPyConnection) -> FaissIndex | None:
    """Return the cached FAISS index, building it on first call."""
    global _CACHE
    if _CACHE is None:
        _CACHE = build_index(conn)
    return _CACHE


def reset_cache() -> None:
    """Invalidate the cached index, forcing a rebuild on next access."""
    global _CACHE
    _CACHE = None


def search(faiss_index: FaissIndex, query_vec: np.ndarray, top_k: int = 3) -> list[int]:
    """Search the index for the top_k nearest chunk ids to query_vec."""
    query = np.asarray(query_vec, dtype=np.float32).reshape(1, -1)
    k = min(top_k, len(faiss_index.id_list))
    if k <= 0:
        return []

    _, positions = faiss_index.index.search(query, k)
    result_ids = []
    for pos in positions[0]:
        if pos < 0:
            continue
        result_ids.append(faiss_index.id_list[pos])
    return result_ids