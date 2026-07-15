---
title: feat: Migrate from LangChain to Pydantic AI with Ollama/llama.cpp
type: feat
status: active
date: 2026-07-13
---

# feat: Migrate from LangChain to Pydantic AI with Ollama/llama.cpp

## Overview

Replace LangChain (`langchain_ollama`, `langchain_core`) with [Pydantic AI](https://pydantic.dev/docs/ai/) as the agent framework, keeping the existing Streamlit UI and local Ollama-backed llama.cpp models. The migration introduces structured output types (the core value-add of Pydantic AI) and simplifies the chat pipeline by removing manual string-prompt construction.

## Problem Frame

The current implementation uses LangChain's `ChatOllama` + `ChatPromptTemplate` to build a raw string prompt and pipe it to `llama3.1` via Ollama. This works but:

- No structured output — responses are plain text with no schema guarantees
- Manual prompt construction (string concatenation in `generate_llama_response`)
- LangChain adds abstraction weight for what is essentially a single chat call
- The README lists RAG and image generation as planned features; Pydantic AI's structured output and tool system make these easier to add later

## Requirements Trace

- **R1.** Replace LangChain with Pydantic AI as the LLM interaction layer
- **R2.** Keep the same Streamlit UI (chat interface, sidebar, message history)
- **R3.** Continue using Ollama with local llama.cpp-backed models (`llama3.1`)
- **R4.** Maintain streaming text output in the chat UI
- **R5.** Introduce structured output types via Pydantic models

## Scope Boundaries

- **Out of scope:** Adding RAG, image generation, or new features — this is a framework migration only
- **Out of scope:** Changing the UI framework (stays on Streamlit)
- **Out of scope:** Docker setup changes (not requested, no Dockerfile exists yet)
- **Out of scope:** Multi-model or model-switching UI

## Context & Research

### Relevant Code and Patterns

- `Chatbot.py` — Main Streamlit entry point, session state management, streaming display loop
- `src/kaiusbot/webapp/helpers.py` — `generate_llama_response()` and `clear_chat_history()`
- `src/kaiusbot/` — Package namespace, currently thin

### External References

- [Pydantic AI OllamaModel docs](https://pydantic.dev/docs/ai/models/ollama/) — `OllamaModel` wraps Ollama's OpenAI-compatible `/v1/chat/completions` endpoint
- [OllamaProvider API](https://pydantic.dev/docs/ai/api/models/ollama/) — `base_url` defaults to `http://localhost:11434/v1`
- [NativeOutput](https://pydantic.dev/docs/ai/output/) — Uses llama.cpp's grammar-constrained decoder (Ollama >= 0.5.0) for schema-valid generation at inference time
- [kai-feinberg/pydantic-agent-example](https://github.com/kai-feinberg/pydantic-agent-example) — Reference Streamlit + Pydantic AI chat template using `agent.run_stream()` with `stream_text(delta=True)`

### Key Technical Findings

- Ollama >= 0.5.0 ships llama.cpp's grammar-constrained decoder → `NativeOutput` produces schema-valid JSON without retries
- `llama3.1` (already in use) supports tool calling; plain `llama3:8b` does not
- Pydantic AI models Ollama via `pydantic-ai-slim[openai]` — the `openai` extra is required because it uses the OpenAI-compatible protocol
- `agent.run_stream()` + `stream_text(delta=True)` replaces the current `chain.invoke()` + manual char iteration pattern

## Key Technical Decisions

- **`OllamaModel` over raw HTTP client:** Pydantic AI provides first-class Ollama support with streaming, structured output, and message history built in
- **`NativeOutput` over `ToolOutput`:** Self-hosted Ollama >= 0.5.0 enforces schema at the llama.cpp grammar level — no retries, no JSON parse errors. Fall back to `ToolOutput` only if the user's Ollama version is older
- **Sync agent over async (initially):** Streamlit's execution model reruns the script top-to-bottom. Use `agent.run_sync_stream()` or wrap async in `asyncio.run()` to keep the code simple — async can be added if latency becomes an issue
- **Keep `st.session_state` for message history:** Pydantic AI's `message_history` parameter accepts a list of `ModelMessage` objects. Convert `st.session_state.messages` to this format rather than introducing a separate session store
- **Single Agent instance:** One `Agent` with a system prompt defined at module level — no agent-per-request factory needed

## Open Questions

### Deferred to Implementation

- **Exact structured output schema:** Depends on what response shape is most useful. Start with a `ChatResponse` model (content + optional metadata) and refine
- **Async vs sync streaming:** The reference pattern uses `async for chunk in result.stream_text()`. Streamlit supports `asyncio.run()` in script mode — verify this works with the current Streamlit version before committing to an async wrapper

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

**Agent module** (`src/kaiusbot/agent.py`) — replaces `helpers.py`:

```
OllamaModel("llama3.1") ──→ Agent(model, system_prompt=..., output_type=NativeOutput(ChatResponse))
                                  │
                                  ├── .run_stream(user_input, message_history=[...])
                                  │       │
                                  │       └── async generator → stream_text(delta=True)
                                  │
                                  └── returns: AgentRunResult (data=ChatResponse, messages=[...])
```

**Streamlit UI** (`Chatbot.py`) — same flow, different backing call:

```
User input → st.chat_input()
    │
    ├── Convert st.session_state.messages → pydantic_ai ModelMessage list
    ├── agent.run_stream(user_input, message_history=messages)
    ├── Iterate stream_text(delta=True) → update st.empty() placeholder
    └── Append ChatResponse.content to st.session_state.messages
```

The `ChatPromptTemplate` + string concatenation in the current `generate_llama_response()` disappears — Pydantic AI's `Agent` handles message formatting internally via its system prompt and `message_history`.

## Implementation Units

- [ ] **Unit 1: Update dependencies and configuration**

**Goal:** Replace LangChain packages with Pydantic AI, configure the Ollama connection

**Requirements:** R1, R3

**Dependencies:** None

**Files:**
- Create: `requirements.txt` (if not present — pin key deps)
- Modify: `install.sh` — add `pip install "pydantic-ai-slim[openai]"`, remove any langchain install steps

**Approach:**
- Remove `langchain-ollama` and `langchain-core` from the project dependencies
- Add `pydantic-ai-slim[openai]` — the `openai` extra is required because `OllamaModel` uses the OpenAI-compatible protocol
- Pin `ollama >= 0.5.0` for llama.cpp grammar-constrained decoding support
- Add `OLLAMA_BASE_URL` env var support (defaults to `http://localhost:11434/v1`)

**Patterns to follow:** Existing `.env` file pattern for configuration

**Test scenarios:**
- Happy path: `pip install -r requirements.txt` succeeds and `from pydantic_ai.models.ollama import OllamaModel` imports cleanly
- Happy path: `OllamaModel("llama3.1")` instantiates without error (does not require a running Ollama server)

**Verification:**
- `pydantic-ai-slim[openai]` installs without conflicts
- `langchain-ollama` and `langchain-core` are no longer imported anywhere

---

- [ ] **Unit 2: Create agent module replacing LangChain helpers**

**Goal:** Replace `src/kaiusbot/webapp/helpers.py` LLM logic with a Pydantic AI Agent

**Requirements:** R1, R3, R5

**Dependencies:** Unit 1

**Files:**
- Create: `src/kaiusbot/agent.py` — Agent definition, response model, streaming helper
- Modify: `src/kaiusbot/webapp/helpers.py` — Remove `generate_llama_response()`, keep `clear_chat_history()` (UI concern)
- Test: `tests/test_agent.py`

**Approach:**
- Define a `ChatResponse` Pydantic model with at minimum a `content: str` field. Add optional fields (`intent: str | None`, `confidence: float | None`) only if they serve a clear purpose
- Instantiate `OllamaModel("llama3.1")` with `OllamaProvider(base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"))`
- Create the `Agent` with a system prompt matching the current one (kAIusbot identity, purpose, top-5 functions)
- Export an async `stream_response(agent, user_input, message_history)` function that yields text deltas
- Keep the model name configurable via env var (`OLLAMA_MODEL`, default `llama3.1`)

**Technical design (directional):**

```
ChatResponse model:
  content: str
  # ponytail: bare minimum structured output — add fields when a consumer needs them

stream_response():
  wraps agent.run_stream(user_input, message_history=pydantic_messages)
  yields deltas via result.stream_text(delta=True)
```

**Patterns to follow:**
- Current system prompt content in `helpers.py` (lines 10-13)
- Standard Pydantic AI Agent instantiation pattern

**Test scenarios:**
- Happy path: `ChatResponse(content="Hello")` validates
- Happy path: `OllamaModel("llama3.1")` instantiates with default provider URL
- Edge case: `stream_response()` handles empty message_history gracefully
- Error path: Clear error message when Ollama server is unreachable
- Integration: Agent with system prompt produces a response that includes "kAIusbot" when asked its name

**Verification:**
- `helpers.py` no longer imports from `langchain_core` or `langchain_ollama`
- `ChatResponse` model validates with `model_validate()`
- Agent instantiates without runtime errors

---

- [ ] **Unit 3: Wire agent into Streamlit UI**

**Goal:** Update `Chatbot.py` to use the Pydantic AI agent instead of LangChain's `ChatOllama`

**Requirements:** R2, R4

**Dependencies:** Unit 2

**Files:**
- Modify: `Chatbot.py` — Replace LangChain imports with agent imports, adapt streaming loop
- Test: `tests/test_ui_integration.py`

**Approach:**
- Replace `from langchain_ollama import ChatOllama` with the agent module
- Replace `llm = ChatOllama(model="llama3.1", ...)` with the Agent instance
- Replace `response = generate_llama_response(llm)` with the `stream_response()` async generator
- Convert `st.session_state.messages` (list of `{role, content}` dicts) to Pydantic AI `ModelMessage` format before passing to the agent
- Keep the existing `st.empty()` + `placeholder.markdown()` streaming pattern, driven by the async generator
- Wrap async call in `asyncio.run()` — Streamlit re-runs the script top-to-bottom each interaction, so there's no persistent event loop to manage

**Patterns to follow:**
- Current streaming display loop in `Chatbot.py` (lines 49-59) — same placeholder pattern, different generator source
- Pydantic AI message format: `ModelRequest(parts=[UserPromptPart(content=...)])` and `ModelResponse(parts=[TextPart(content=...)])`

**Test scenarios:**
- Happy path: User types "Hello" → assistant response streams in and displays
- Happy path: "What is your name?" → response contains "kAIusbot"
- Edge case: Empty message history on first load → default assistant greeting displayed
- Edge case: Rapid consecutive messages → each gets its own response
- Error path: Ollama server down → user sees a clear error message, not a traceback

**Verification:**
- App launches with `streamlit run Chatbot.py` (manually verified)
- No `langchain` imports remain in `Chatbot.py`
- Message history persists correctly across reruns

---

- [ ] **Unit 4: Update install.sh and verify llama.cpp integration**

**Goal:** Ensure install script pulls compatible models and verify structured output works via llama.cpp grammar constraints

**Requirements:** R3, R5

**Dependencies:** Unit 3

**Files:**
- Modify: `install.sh` — Remove `ollama pull llama2:7b`, keep `llama3.1`, add version check
- Test: `tests/test_structured_output.py`

**Approach:**
- Remove `llama2:7b` from install script (doesn't support tool calling)
- Add `ollama --version` check with >= 0.5.0 requirement comment for llama.cpp grammar support
- Keep `llama3.1` as the default model
- Verify `NativeOutput(ChatResponse)` works end-to-end: agent returns a validated `ChatResponse` instance, not raw text

**Test scenarios:**
- Happy path: Agent with `NativeOutput(ChatResponse)` returns a `ChatResponse` object (not a parse error)
- Happy path: Response content is non-empty string
- Edge case: Model produces text that doesn't match schema → Pydantic AI handles fallback (not a crash)

**Verification:**
- `install.sh` only pulls supported models
- Structured output agent returns typed `ChatResponse`, not raw text
- `ollama --version` >= 0.5.0 confirmed (needed for grammar-constrained decoding)

## System-Wide Impact

- **Interaction graph:** `Chatbot.py` → `src/kaiusbot/agent.py` → `OllamaModel` → Ollama server (localhost:11434). No other entry points affected.
- **Error propagation:** Agent failures (Ollama down, model not found) should surface as `st.error()` messages in the UI, not uncaught exceptions
- **State lifecycle risks:** `st.session_state.messages` format changes subtly — current format is `[{role, content}]`, Pydantic AI uses `ModelMessage` objects. Keep session state in the simple dict format and convert at the boundary
- **Unchanged invariants:** `clear_chat_history()` behavior preserved; sidebar UI unchanged; LinkedIn/GitHub links unchanged; page title and caption unchanged

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| `llama3.1` produces malformed structured output under `NativeOutput` | llama.cpp grammar constraints prevent this at generation time for Ollama >= 0.5.0. If issues arise, fall back to `ToolOutput` |
| Streamlit + asyncio compatibility | `asyncio.run()` in a script rerun context is well-tested. If issues arise, switch to sync `agent.run()` + manual char iteration |
| Ollama server not running | Catch connection errors and display `st.error("Ollama server not reachable at ...")` instead of a traceback |

## Sources & References

- [Pydantic AI OllamaModel docs](https://pydantic.dev/docs/ai/models/ollama/)
- [Pydantic AI OllamaProvider API](https://pydantic.dev/docs/ai/api/models/ollama/)
- [Pydantic AI Structured Output (NativeOutput)](https://pydantic.dev/docs/ai/output/)
- [kai-feinberg/pydantic-agent-example](https://github.com/kai-feinberg/pydantic-agent-example) — Streamlit + Pydantic AI template
- Related code: `Chatbot.py`, `src/kaiusbot/webapp/helpers.py`
