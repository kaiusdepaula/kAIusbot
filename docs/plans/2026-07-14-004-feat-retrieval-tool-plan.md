---
title: feat: Add local vector-db retrieval tool
type: feat
status: active
date: 2026-07-14
---

# feat: Add local vector-db retrieval tool

## Overview

Add a new agent tool, `retrieve_docs`, that lets the agent answer natural-language queries by searching a local vector database built from the project's own markdown documentation (`docs/`). This follows the same "local, zero-dependency, no external API" philosophy already established for the other tools in [`src/agent.py`](../../src/agent.py).

## Problem Frame

The agent currently has no way to look up unstructured knowledge — it can query MLflow's SQLite database ([`query_mlflow`](../../src/agent.py:126)) but has no semantic search over free text. Adding a retrieval-augmented tool lets the agent answer questions like "what did we decide about MLflow tracing?" or "summarize the tool plan" by pulling relevant chunks from `docs/` instead of relying purely on the LLM's memory.

## Requirements Trace

- **R1.** A one-time/rerunnable ingestion script chunks and embeds markdown files under `docs/` and persists them to a local vector store.
- **R2.** A new `@agent.tool` (`retrieve_docs`) embeds an incoming NLU query, performs similarity search against the store, and returns the most relevant chunk(s) with source citations.
- **R3.** The system works fully offline/local — no external embedding API calls.
- **R4.** The tool degrades gracefully (clear message, no crash) if ingestion hasn't been run yet or the store is empty.
- **R5.** Existing chat behavior (streaming, session state, other tools) is unaffected.

## Scope Boundaries

- **Out of scope:** Automatic/real-time re-indexing on file change — ingestion is a manual/CLI step for now.
- **Out of scope:** Non-markdown content (PDFs, code, chat history) — future extension.
- **Out of scope:** Hybrid/keyword search, re-ranking models — pure dense vector similarity for v1.

## Context & Research

### Relevant Code and Patterns

- [`src/agent.py`](../../src/agent.py) — Agent + tools live here (`@agent.tool` / `@agent.tool_plain`). `query_mlflow` ([`src/agent.py:126`](../../src/agent.py:126)) is the closest existing pattern: local SQLite read, string formatting of tabular results, defensive error handling with plain error strings.
- [`docs/plans/2026-07-13-002-feat-agent-tools-plan.md`](2026-07-13-002-feat-agent-tools-plan.md) — established conventions: tools return strings, use `RunContext[None]` for typed-param tools, keep everything local, no crashes on malformed input.
- `pyproject.toml` — dependency list is currently minimal (`streamlit`, `pydantic-ai-slim[mcp,openai]`, `mlflow`, `litecli`). New deps must be added here.

### Key Technical Decisions

- **Embedding model:** `sentence-transformers/all-MiniLM-L6-v2` — small (~80MB), fast on CPU, 384-dim, fully offline once downloaded.
- **Persistent store:** DuckDB file (`vector_store.duckdb`) holding one row per chunk: `id`, `source_path`, `chunk_index`, `text`, `embedding` (stored as a `FLOAT[384]` array column, or a `BLOB` of packed float32 bytes if DuckDB's array support is inconvenient in the installed version).
- **Retrieval index:** FAISS `IndexFlatIP` over L2-normalized embeddings (cosine similarity via inner product). Built in-memory from all rows in DuckDB, lazily on first tool call in a process, and cached as a module-level singleton for the process lifetime. Flat index is appropriate given the expected small corpus size (a handful of markdown docs); no need for IVF/HNSW.
- **Chunking:** Split markdown by headings first, then by paragraphs within a heading section, merging/splitting to target a chunk size (~300–500 words) with a small overlap (~50 words) between adjacent chunks to preserve context across boundaries.
- **Ingestion trigger:** Manual CLI script (`scripts/ingest.py`), rerunnable, with a `--reset` flag to drop and rebuild the table (idempotent otherwise via delete-by-source-path + reinsert).
- **Module layout:** New `src/retrieval/` package (`embedder.py`, `chunking.py`, `store.py`, `index.py`) — kept separate from `src/agent.py` since this is a distinct subsystem with its own multi-file structure, unlike the trivial single-function tools already in `agent.py`.

## Open Questions

### Deferred to Implementation

- **Exact chunk size/overlap tuning:** Start with ~400 words / 50-word overlap; adjust if retrieval quality on test queries is poor.
- **DuckDB array vs. blob storage for embeddings:** Try native `FLOAT[384]` array column first; fall back to a serialized blob (`np.ndarray.tobytes()`) if the installed DuckDB version's array/vector support is limited.

## Implementation Units

- [ ] **Unit 1: Add dependencies**

**Goal:** Make `sentence-transformers`, `duckdb`, and `faiss-cpu` available to the project.

**Requirements:** R1, R2, R3

**Files:**
- Modify: `pyproject.toml` — add `sentence-transformers`, `duckdb`, `faiss-cpu` to `dependencies`.

**Verification:** `uv sync` completes without errors; `python -c "import sentence_transformers, duckdb, faiss"` succeeds.

---

- [ ] **Unit 2: Embedding wrapper**

**Goal:** Provide a single, reusable function to embed text using the chosen local model.

**Requirements:** R1, R2, R3

**Files:**
- Create: `src/retrieval/__init__.py`
- Create: `src/retrieval/embedder.py`

**Approach:**
- Lazily load `SentenceTransformer("all-MiniLM-L6-v2")` once (module-level singleton / `functools.lru_cache`) to avoid reloading the model on every call.
- Expose `embed(texts: list[str]) -> np.ndarray` returning L2-normalized float32 vectors (normalize so FAISS inner product == cosine similarity).
- Expose `embed_query(text: str) -> np.ndarray` as a convenience wrapper for a single string.

**Verification:** `embed(["hello world"])` returns a `(1, 384)` float32 array with unit norm.

---

- [ ] **Unit 3: Markdown-aware chunking**

**Goal:** Split markdown documents into overlapping chunks suitable for embedding.

**Requirements:** R1

**Files:**
- Create: `src/retrieval/chunking.py`

**Approach:**
- `chunk_markdown(text: str, target_words: int = 400, overlap_words: int = 50) -> list[str]`.
- Split on markdown headings (`^#+ `) to get sections; within long sections, split further on blank-line-separated paragraphs; merge small paragraphs together up to `target_words`; add `overlap_words` from the end of the previous chunk to the start of the next when splitting a large section.
- Guard against empty/whitespace-only input (return empty list).

**Verification:** Feed in `docs/summaries/mlflow-pydantic-ai-tracing.md` — confirm output is a list of non-empty strings, each under roughly 1.5x `target_words`, with visible overlap between consecutive chunks.

---

- [ ] **Unit 4: DuckDB store**

**Goal:** Persist chunks + embeddings and support fetch-by-id and reset/delete-by-source operations.

**Requirements:** R1, R4

**Files:**
- Create: `src/retrieval/store.py`

**Approach:**
- `connect(db_path: str = "vector_store.duckdb") -> duckdb.DuckDBPyConnection`.
- `init_schema(conn)` — `CREATE TABLE IF NOT EXISTS chunks (id BIGINT PRIMARY KEY, source_path TEXT, chunk_index INTEGER, text TEXT, embedding FLOAT[384])` (fall back to `BLOB` for embedding if array type proves awkward with the installed DuckDB version).
- `upsert_chunks(conn, source_path, chunks: list[str], embeddings: np.ndarray)` — delete existing rows for `source_path` then insert fresh rows (idempotent re-ingestion of a changed file).
- `fetch_by_ids(conn, ids: list[int]) -> list[dict]` — returns `text`, `source_path`, `chunk_index` for given ids, used after FAISS search.
- `fetch_all(conn) -> tuple[list[int], np.ndarray]` — returns all `(id, embedding)` pairs, used to build the FAISS index.
- `reset(conn)` — drop and recreate the table (used by `--reset` in ingestion).

**Verification:** Round-trip test — insert a few chunks, `fetch_all` returns matching ids/embeddings, `fetch_by_ids` returns matching text.

---

- [ ] **Unit 5: FAISS index wrapper**

**Goal:** Build an in-memory FAISS index from the DuckDB store and expose a top-k search function.

**Requirements:** R2, R4

**Files:**
- Create: `src/retrieval/index.py`

**Approach:**
- `build_index(conn) -> tuple[faiss.IndexFlatIP, list[int]] | None` — loads all embeddings via `store.fetch_all`, returns `None` if the table is empty (empty-index case for R4), otherwise builds `IndexFlatIP(dim)` and `add`s the vectors, returning the index plus the id list (FAISS internal indices map positionally to this list since row ids aren't guaranteed contiguous).
- `search(index, id_list, query_vec, top_k=3) -> list[int]` — runs `index.search`, maps returned positional indices back to DuckDB row ids via `id_list`, filters out `-1`/invalid results.
- Module-level cache: build once per process, rebuild only if explicitly invalidated (e.g., a `reset_cache()` function) — simplest approach for a chat app where ingestion happens out-of-process before the app starts.

**Verification:** With a store containing known chunks, embedding a query similar to one chunk's text returns that chunk's id as the top result.

---

- [ ] **Unit 6: Ingestion CLI script**

**Goal:** Walk `docs/`, chunk and embed each markdown file, and persist to the DuckDB store.

**Requirements:** R1

**Files:**
- Create: `scripts/ingest.py`

**Approach:**
- `argparse` with `--docs-dir` (default `docs/`), `--db-path` (default `vector_store.duckdb`), `--reset` flag.
- Walk `docs/` recursively for `*.md` files (`pathlib.Path.rglob("*.md")`).
- For each file: read text → `chunking.chunk_markdown` → `embedder.embed` → `store.upsert_chunks`.
- Print a per-file summary (chunk count) and a final total.
- If `--reset` is passed, call `store.reset(conn)` before processing any files.

**Verification:** `uv run python scripts/ingest.py --reset` completes, prints chunk counts per file, and `vector_store.duckdb` is created with rows (spot-check via `duckdb.connect(...).sql("SELECT COUNT(*) FROM chunks")`).

---

- [ ] **Unit 7: `retrieve_docs` agent tool**

**Goal:** Expose retrieval to the agent as a callable tool.

**Requirements:** R2, R4, R5

**Files:**
- Modify: `src/agent.py` — add `retrieve_docs` tool near `query_mlflow`.

**Approach:**
- `@agent.tool def retrieve_docs(ctx: RunContext[None], query: str = "", top_k: int = 3) -> str`.
- Docstring: clarifies this searches the local project documentation (not the web) for relevant background/context.
- On call: open/reuse a DuckDB connection, build/reuse the cached FAISS index (Unit 5), embed the query (Unit 2), search, fetch chunk text (Unit 4), and format as a numbered list with `source_path` citations, e.g. `1. [docs/summaries/foo.md] <chunk text>`.
- Empty query → `"Error: empty query"`.
- Empty/missing index → `"No documents have been indexed yet. Run scripts/ingest.py to build the index."` (R4).
- Wrap embedding/search/DB calls in a `try/except` returning an error string on failure, consistent with other tools' no-crash guarantee.

**Patterns to follow:** Same shape as `query_mlflow` — plain string return, defaults for all params, error strings instead of exceptions.

**Verification:**
- `len(agent._function_tools)` increases by 1.
- Manual chat test: ask a question whose answer lives in `docs/summaries/mlflow-pydantic-ai-tracing.md`; confirm the agent calls `retrieve_docs` and incorporates the retrieved text.
- MLflow trace (`mlflow ui --backend-store-uri sqlite:///mlflow.db`) shows a `retrieve_docs` tool-call child span.

---

- [ ] **Unit 8: Housekeeping**

**Goal:** Keep the repo clean and documented.

**Requirements:** R5

**Files:**
- Modify: `.gitignore` — add `vector_store.duckdb` (and any DuckDB WAL sidecar files, e.g. `*.duckdb.wal`).
- Modify: `README.md` — add a short "Retrieval" section describing `scripts/ingest.py` usage and the new `retrieve_docs` tool.

**Verification:** `git status` after ingestion shows the DuckDB file is ignored; README renders correctly.

## System-Wide Impact

- **Interaction graph:** `scripts/ingest.py` (offline, manual) → `vector_store.duckdb` ← `src/agent.py`'s `retrieve_docs` tool (online, per-chat-turn) → FAISS in-memory index (built from DuckDB at first use per process).
- **Error propagation:** All retrieval failures (missing DB, empty index, embedding errors) surface as plain error strings from the tool — never raise into the streaming loop, matching existing tool conventions.
- **Unchanged invariants:** `stream_response()` signature, `main.py` UI logic, and all existing tools remain untouched.
- **Integration coverage:** Full chain exercised by: `ingest.py` run once → chat query → `retrieve_docs` tool call → FAISS search → DuckDB fetch → agent response.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| `sentence-transformers` model download requires network on first run | Document this in README; model caches locally afterward (fully offline for subsequent runs) |
| DuckDB native array/vector column type unsupported in installed version | Fall back to `BLOB` storage of packed float32 bytes, deserialized with `np.frombuffer` |
| FAISS index staleness if `docs/` changes after the app has started | Acceptable for v1 — document that re-running `scripts/ingest.py` requires restarting the chat app to pick up new content; could add a `reset_cache()`/file-watch trigger later |
| Corpus grows large enough that `IndexFlatIP` becomes slow | Not a concern at current `docs/` scale; swap to `IndexHNSWFlat` later if needed |
| Tool called before ingestion has ever run | `build_index` returns `None` for an empty table; tool detects this and returns a clear instructional message (R4) |

## Sources & References

- Related code: [`src/agent.py:104-154`](../../src/agent.py) (`query_mlflow` pattern to mirror)
- Related plan: [`docs/plans/2026-07-13-002-feat-agent-tools-plan.md`](2026-07-13-002-feat-agent-tools-plan.md)
- [Sentence-Transformers docs](https://www.sbert.net/) — `all-MiniLM-L6-v2` model card
- [FAISS wiki](https://github.com/facebookresearch/faiss/wiki) — `IndexFlatIP` usage
- [DuckDB Python API docs](https://duckdb.org/docs/api/python/overview)