---
title: fix: Tool call event handling and post-migration cleanup
type: fix
status: active
date: 2026-07-13
---

# fix: Tool call event handling and post-migration cleanup

## Overview

Fix two bugs in the Streamlit + Pydantic AI streaming pipeline and clean up references left stale by the LangChain migration. The core fix is splitting `FunctionToolCallEvent` handling — it currently fires both `tool_call` and `tool_result` from the same event, so the UI indicator appears and vanishes instantly without the tool actually having returned.

## Problem Frame

The LangChain → Pydantic AI migration (plan 001) and tool addition (plan 002) left three issues:

1. **`stream_response` yields `tool_result` prematurely.** The `FunctionToolCallEvent` handler yields `{"type": "tool_result", ...}` immediately after `{"type": "tool_call", ...}`. But the `FunctionToolCallEvent` only signals the model's *intent* to call a tool — the tool hasn't executed yet. Pydantic AI 1.107.1 has `FunctionToolResultEvent` (the actual completion signal), which is never imported or handled. Result: the UI's "Calling `tool`..." indicator flashes on/off instantly, and the real tool completion is invisible to the UI layer.

2. **`asyncio.run()` can fail in Streamlit.** When Streamlit's own async runtime has a running event loop, `asyncio.run(_stream())` raises `RuntimeError: asyncio.run() cannot be called from a running event loop`. This varies by Streamlit version and config, but when it hits, the app is dead.

3. **Post-migration staleness.** README says `streamlit run Chatbot.py` (file deleted, now `main.py`). `src/__init__.py` does `from src.webapp.helpers import *` (wildcard re-export of `clear_chat_history`). `install.sh` pulls `gpt-oss:20b` but README model table shows `llama3.1`.

## Requirements Trace

- **R1.** Tool call events stream correctly: `tool_call` fires when the model initiates a call, `tool_result` fires when the tool returns
- **R2.** The "Calling `tool`..." indicator stays visible during tool execution and clears on completion
- **R3.** `asyncio.run()` pattern handles running-event-loop environments without crashing
- **R4.** README, `__init__.py`, and `install.sh` references match the actual file layout and model

## Scope Boundaries

- **Out of scope:** Restructuring the agent module or Streamlit UI beyond the event loop and cleanup fixes
- **Out of scope:** Adding new features, tools, or model changes
- **Out of scope:** `.env` key rotation (`.env` is gitignored, keys are local only)

## Context & Research

### Relevant Code and Patterns

- `src/agent.py:187-194` — The `stream_response` event loop with the buggy `FunctionToolCallEvent` handler
- `main.py:47-68` — Streamlit async stream wrapper with `asyncio.run()`
- `main.py:50-61` — UI event handlers: `tool_call` sets `tool_name`, `tool_result` clears it
- Pydantic AI 1.107.1 event types confirmed available: `FunctionToolCallEvent` (has `part.tool_name`), `FunctionToolResultEvent` (has `part.tool_name` via `ToolReturnPart`)

### Key Technical Findings

- `BaseToolCallPart` defines `tool_name: str` — inherited by `ToolCallPart`, accessible as `event.part.tool_name`
- `ToolReturnPart` also inherits `tool_name` from `BaseToolReturnPart` — `event.part.tool_name` works for both event types
- `FunctionToolResultEvent` init signature: `(part: ToolReturnPart | RetryPromptPart | None, ...)` — same `event.part.tool_name` access pattern
- Streamlit's script rerun model: `asyncio.run()` works when no loop runs, fails with `RuntimeError` when a loop is active

## Key Technical Decisions

- **Split `FunctionToolCallEvent` into separate call/result handlers:** One line change each — import `FunctionToolResultEvent`, handle it separately. No new abstractions.
- **Use `asyncio.run()` with a thread fallback:** Try `asyncio.run()` first (covers the common case). If it fails with a running-event-loop error, run the coroutine in a daemon thread. No new dependencies, 6 extra lines.
- **Fix README and `__init__.py` inline:** Direct text fixes, no restructuring.

## Implementation Units

- [ ] **Unit 1: Fix tool call event handling in `stream_response`**

**Goal:** `tool_call` and `tool_result` events stream at the correct times

**Requirements:** R1, R2

**Dependencies:** None

**Files:**
- Modify: `src/agent.py`

**Approach:**
- Add `FunctionToolResultEvent` to the import from `pydantic_ai.messages`
- Split the current `FunctionToolCallEvent` case into two: one for call, one for result
- Yield only `{"type": "tool_call", "name": event.part.tool_name}` on `FunctionToolCallEvent`
- Yield `{"type": "tool_result", "name": event.part.tool_name}` on `FunctionToolResultEvent`

**Technical design (directional):**

```
# In stream_response event loop — replace lines 189-194:

case FunctionToolCallEvent():
    yield {"type": "tool_call", "name": event.part.tool_name}
case FunctionToolResultEvent():
    yield {"type": "tool_result", "name": event.part.tool_name}
```

**Patterns to follow:** Existing `match`/`case` pattern in `stream_response` (lines 189-194)

**Test scenarios:**
- Happy path: Ask agent "what time is it?" → "Calling `get_current_time`..." indicator appears and stays → indicator clears when time result arrives → time displayed in chat
- Happy path: Chat without tool use → no tool_call/tool_result events fired, text streams normally
- Edge case: Tool that errors (e.g., calculator with division by zero) → `tool_result` still fires, indicator clears, error string shown
- Edge case: Multiple tool calls in one turn → each call/result pair fires independently

**Verification:**
- `FunctionToolResultEvent` is imported and handled
- "Calling `tool`..." indicator visible during tool execution (not a flicker)
- Streaming text before and after tool calls renders correctly

---

- [ ] **Unit 2: Harden `asyncio.run()` for Streamlit compatibility**

**Goal:** `main.py` doesn't crash when Streamlit has a running event loop

**Requirements:** R3

**Dependencies:** None (independent of Unit 1)

**Files:**
- Modify: `main.py`

**Approach:**
- Wrap `asyncio.run(_stream())` in a try/except for `RuntimeError`
- On "running event loop" error, run `_stream()` in a daemon thread with its own `asyncio.run()` and block on completion
- ponytail: thread-based fallback, no new dependencies

**Technical design (directional):**

```python
# Replace lines 63-64 in main.py:
try:
    asyncio.run(_stream())
except RuntimeError:
    # ponytail: Streamlit has a running event loop — run in a fresh thread
    import threading
    done = threading.Event()
    def _run():
        asyncio.run(_stream())
        done.set()
    threading.Thread(target=_run, daemon=True).start()
    done.wait()
```

**Patterns to follow:** Existing error handling on line 65-66

**Test scenarios:**
- Happy path: Normal Streamlit run → `asyncio.run()` succeeds, response streams as before
- Edge case: Streamlit with running event loop → falls back to thread, response still streams
- Error path: Genuine RuntimeError (not event-loop-related) → still caught by outer try/except on line 65

**Verification:**
- App launches and responds correctly in both `streamlit run` and `python main.py` (if applicable)
- No "cannot be called from a running event loop" crash

---

- [ ] **Unit 3: Clean up stale references from migration**

**Goal:** README, `__init__.py`, and `install.sh` match the actual project layout

**Requirements:** R4

**Dependencies:** None

**Files:**
- Modify: `README.md` — `Chatbot.py` → `main.py`, model name to `gpt-oss:20b`
- Modify: `src/__init__.py` — Replace wildcard import with explicit re-export

**Approach:**
- README line 27: Change `uv run streamlit run Chatbot.py` to `uv run streamlit run main.py`
- README model table: Change default `llama3.1` → `gpt-oss:20b` (matching `.env` and `install.sh`)
- `src/__init__.py`: Replace `from src.webapp.helpers import *` with `from src.webapp.helpers import clear_chat_history`
- ponytail: explicit import over wildcard — one line, same behavior, no surprise re-exports

**Patterns to follow:** Current README structure, current `__init__.py` pattern

**Test scenarios:**
- Happy path: `from src import clear_chat_history` works
- Happy path: README commands produce a running app when copy-pasted

**Verification:**
- `python -c "from src import clear_chat_history"` succeeds
- README run command matches actual filename

---

## System-Wide Impact

- **Interaction graph:** `main.py` → `stream_response()` → Pydantic AI agent. Event types in the stream change slightly (two separate events instead of one doubled event), but the UI contract (`{"type": "tool_call"|"tool_result", "name": str}`) is unchanged.
- **Error propagation:** Unit 2 adds a thread fallback — failures inside the thread still propagate via the `full_response[0]` assignment pattern.
- **Unchanged invariants:** `stream_response()` signature unchanged; `clear_chat_history()` unchanged; Streamlit session state format unchanged; `st.chat_input()` flow unchanged; tool definitions unchanged.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| `ToolReturnPart` doesn't have `tool_name` like `ToolCallPart` does | Checked: `BaseToolReturnPart` source confirms `tool_name: str` field. If it's absent at runtime, fall back to `event.part.tool_name if hasattr(event.part, 'tool_name') else "unknown"` |
| Thread fallback in Unit 2 introduces subtle concurrency issues with Streamlit | `done.wait()` blocks the main thread until the stream completes — same synchronous behavior as before, just running the loop in a different thread |

## Sources & References

- Pydantic AI 1.107.1 source: `BaseToolCallPart`, `BaseToolReturnPart`, `FunctionToolCallEvent`, `FunctionToolResultEvent`
- Related code: `src/agent.py:187-194`, `main.py:47-68`, `src/webapp/helpers.py`
- Related plans: `docs/plans/2026-07-13-001-feat-pydantic-ai-migration-plan.md`, `docs/plans/2026-07-13-002-feat-agent-tools-plan.md`
