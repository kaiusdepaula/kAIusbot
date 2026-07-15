# Changelog

## 2026-07-15 — Agent config + Streamlit sidebar

**Agent refactor** (`src/agent.py`):
- Replaced module-level `agent` global with lazy `_get_agent()` — rebuilds when
  model name or base URL change, cached otherwise
- Tools moved from `@agent.tool` decorators to a `tools=[...]` list passed at
  init, so the agent can be rebuilt with the same tool set
- `stream_response` accepts `temperature` (passed as `model_settings` to the
  inference call) and `model_name`/`base_url` overrides
- `retrieve_docs` falls back to a module-level `_retrieval_top_k` (default 3)
  when the agent doesn't specify `top_k`; settable via `set_retrieval_top_k()`

**Streamlit sidebar** (`main.py`):
- Model name and API base URL text inputs
- Temperature slider (0.0–2.0, step 0.1, default 0.7)
- Top-N selector (1/2/3/5/7/10) for doc retrieval
- GitHub badge alongside LinkedIn badge
- All config persisted in `st.session_state`, flows through to agent calls

**ROCm fix** (`pyproject.toml`, `docs/troubleshooting-rocm-uv.md`):
- Removed `+rocm7.2` local version from PEP 508 dependency strings
- Dropped dead `pytorch-triton-rocm`/`triton-rocm` source overrides
- Added `triton-rocm>=3.7.1` as direct dependency so `explicit = true` index
  resolves it (transitive deps don't inherit explicit index routing)
