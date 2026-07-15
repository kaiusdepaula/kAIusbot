# kAIusbot

Personal agent development lab. Break things, test ideas, figure out what works.

## Stack

- **Web UI:** Streamlit
- **Agent framework:** pydantic-ai (OpenAI-compatible, Ollama backend)
- **Tracing:** MLflow
- **Vector retrieval:** sentence-transformers + DuckDB (local, offline)
- **Python:** 3.11+ via uv

## Setup

```bash
./install.sh          # Ollama + models
uv sync               # Python deps
```

## Run

```bash
uv run streamlit run main.py       # Chat UI → http://localhost:8501
uv run python scripts/ingest.py    # Build doc index (optional)
mlflow ui --backend-store-uri sqlite:///mlflow.db  # Traces
```

## Project layout

```
src/
  agent.py           # Agent definition, tools, streaming
  retrieval/         # Local vector search (chunk, embed, index, store)
  webapp/            # Streamlit UI
  prompts/           # System prompts
scripts/
  ingest.py          # Build/rebuild the docs vector index
docs/
  troubleshooting/   # Fix notes (e.g., ROCm + uv)
```
