"""DuckDB-backed persistent store for embedded document chunks.

Embeddings are stored as BLOBs of packed float32 bytes (via
`np.ndarray.tobytes()` / `np.frombuffer()`) for maximum compatibility across
DuckDB versions, rather than relying on native array/vector column types.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np

from src.retrieval.embedder import EMBEDDING_DIM

DEFAULT_DB_PATH = "vector_store.duckdb"


def connect(db_path: str = DEFAULT_DB_PATH) -> duckdb.DuckDBPyConnection:
    """Open a connection to the DuckDB vector store, creating the schema if needed."""
    conn = duckdb.connect(db_path)
    init_schema(conn)
    return conn


def init_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the chunks table and id sequence if they don't already exist."""
    conn.execute("CREATE SEQUENCE IF NOT EXISTS chunks_id_seq START 1")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chunks (
            id BIGINT PRIMARY KEY DEFAULT nextval('chunks_id_seq'),
            source_path TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            text TEXT NOT NULL,
            embedding BLOB NOT NULL
        )
        """
    )


def reset(conn: duckdb.DuckDBPyConnection) -> None:
    """Drop and recreate the chunks table, discarding all existing data."""
    conn.execute("DROP TABLE IF EXISTS chunks")
    conn.execute("DROP SEQUENCE IF EXISTS chunks_id_seq")
    init_schema(conn)


def upsert_chunks(
    conn: duckdb.DuckDBPyConnection,
    source_path: str,
    chunks: list[str],
    embeddings: np.ndarray,
) -> int:
    """Replace all chunks for `source_path` with the given chunks/embeddings.

    Returns the number of chunks inserted.
    """
    if len(chunks) != len(embeddings):
        raise ValueError("chunks and embeddings must have the same length")

    conn.execute("DELETE FROM chunks WHERE source_path = ?", [source_path])

    if not chunks:
        return 0

    for chunk_index, (text, vector) in enumerate(zip(chunks, embeddings)):
        blob = np.asarray(vector, dtype=np.float32).tobytes()
        conn.execute(
            "INSERT INTO chunks (source_path, chunk_index, text, embedding) VALUES (?, ?, ?, ?)",
            [source_path, chunk_index, text, blob],
        )

    return len(chunks)


def fetch_all(conn: duckdb.DuckDBPyConnection) -> tuple[list[int], np.ndarray]:
    """Fetch all (id, embedding) pairs from the store.

    Returns an empty list and an empty (0, EMBEDDING_DIM) array if the store is empty.
    """
    rows = conn.execute("SELECT id, embedding FROM chunks ORDER BY id").fetchall()
    if not rows:
        return [], np.empty((0, EMBEDDING_DIM), dtype=np.float32)

    ids = [row[0] for row in rows]
    vectors = np.stack([np.frombuffer(row[1], dtype=np.float32) for row in rows])
    return ids, vectors


def fetch_by_ids(conn: duckdb.DuckDBPyConnection, ids: list[int]) -> list[dict]:
    """Fetch text/source_path/chunk_index for the given chunk ids, preserving input order."""
    if not ids:
        return []

    placeholders = ", ".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT id, source_path, chunk_index, text FROM chunks WHERE id IN ({placeholders})",
        ids,
    ).fetchall()

    by_id = {row[0]: {"id": row[0], "source_path": row[1], "chunk_index": row[2], "text": row[3]} for row in rows}
    return [by_id[i] for i in ids if i in by_id]


def is_empty(conn: duckdb.DuckDBPyConnection) -> bool:
    """Return True if the chunks table has no rows."""
    count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    return count == 0


def ensure_db_dir(db_path: str) -> None:
    """Ensure the parent directory of db_path exists (no-op if it's the cwd)."""
    parent = Path(db_path).parent
    if str(parent) not in ("", "."):
        parent.mkdir(parents=True, exist_ok=True)