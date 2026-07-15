#!/usr/bin/env python
"""Ingest markdown files into the local vector store for retrieval.

Walks a directory (default: docs/) for *.md files, chunks each one,
embeds the chunks with sentence-transformers, and upserts them into the
DuckDB vector store used by the agent's `retrieve_docs` tool.

Usage:
    uv run python scripts/ingest.py
    uv run python scripts/ingest.py --docs-dir docs --db-path vector_store.duckdb
    uv run python scripts/ingest.py --reset
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as `python scripts/ingest.py` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.retrieval import chunking, embedder, store  # noqa: E402


def ingest(docs_dir: str, db_path: str, reset: bool) -> None:
    store.ensure_db_dir(db_path)
    conn = store.connect(db_path)

    if reset:
        print(f"Resetting vector store at {db_path}...")
        store.reset(conn)

    docs_path = Path(docs_dir)
    md_files = sorted(docs_path.rglob("*.md"))

    if not md_files:
        print(f"No markdown files found under {docs_dir}")
        conn.close()
        return

    total_chunks = 0
    for md_file in md_files:
        text = md_file.read_text(encoding="utf-8")
        chunks = chunking.chunk_markdown(text)

        if not chunks:
            print(f"  {md_file}: no content, skipped")
            continue

        embeddings = embedder.embed(chunks)
        source_path = str(md_file.relative_to(docs_path.parent) if docs_path.parent != Path(".") else md_file)
        count = store.upsert_chunks(conn, source_path, chunks, embeddings)
        total_chunks += count
        print(f"  {source_path}: {count} chunks")

    conn.close()
    print(f"\nDone. Indexed {len(md_files)} files, {total_chunks} chunks total.")
    print("Restart the chat app to pick up the updated index.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs-dir", default="docs", help="Directory to walk for markdown files (default: docs)")
    parser.add_argument(
        "--db-path", default=store.DEFAULT_DB_PATH, help=f"Path to the DuckDB vector store (default: {store.DEFAULT_DB_PATH})"
    )
    parser.add_argument("--reset", action="store_true", help="Drop and rebuild the vector store before ingesting")
    args = parser.parse_args()

    ingest(args.docs_dir, args.db_path, args.reset)


if __name__ == "__main__":
    main()