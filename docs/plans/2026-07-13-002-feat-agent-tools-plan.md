---
title: feat: Add tools to agent for MLflow tracing
type: feat
status: active
date: 2026-07-13
---

# feat: Add tools to agent for MLflow tracing

## Overview

Add a set of Pydantic AI tools to the agent so tool calls appear in MLflow traces (`mlflow.pydantic_ai.autolog()`). The agent currently has zero tools — every conversation is a single flat span. Tools create child spans in the trace, covering the full agent loop: LLM call → tool invocation → LLM call with tool result.

## Problem Frame

MLflow autologging for Pydantic AI captures the agent run as a trace. Without tools, the trace is just one LLM span. Adding tools exercises the tracing path that matters: tool selection, tool execution (as child spans), and the agent incorporating tool results into its response. This is what the user wants to test.

## Requirements Trace

- **R1.** Agent has a set of registered tools that are naturally discoverable via conversation
- **R2.** Tool calls appear as child spans in MLflow traces
- **R3.** Tools return structured results the agent can weave into responses
- **R4.** Existing chat behavior (streaming, session state) is unaffected

## Scope Boundaries

- **Out of scope:** External API tools (weather, search, etc.) — keep it local and zero-dependency
- **Out of scope:** Tool approval/confirmation UI — tools run automatically, matching the current no-confirmation chat flow
- **Out of scope:** Dynamic tool registration or runtime tool config

## Context & Research

### Relevant Code and Patterns

- `src/agent.py` — Agent defined as `Agent(model, system_prompt=SYSTEM_PROMPT, instrument=True)`. Tools are added via the `@agent.tool` decorator (plain functions) or `@agent.tool_plain` (no args besides ctx).
- `main.py` — Streamlit UI, calls `stream_response()` async generator. No changes needed here.
- Pydantic AI tools: `RunContext` is injected automatically when the first param is typed `RunContext`. Return values can be plain dicts, Pydantic models, or strings.

### Key Technical Decisions

- **`@agent.tool` over `@agent.tool_plain`:** `tool` lets tools declare typed parameters (with docstrings) so the LLM can discover and invoke them correctly. `tool_plain` gets no agent-exposed parameters — only useful for context-only tools.
- **Keep tools in same file as agent:** The agent instance is the registry. Tools are defined in the same module as `agent` for simplicity — separate them only if the file grows unwieldy.
- **Tools return strings or simple dicts:** No need for Pydantic return models yet. MLflow captures the return value regardless of type.

## Open Questions

### Deferred to Implementation

- **Exact tool names and descriptions:** The LLM uses function name + docstring to decide when to call. Start with the obvious names and tune docstrings if the agent calls the wrong tool or misses calls.

## Implementation Units

- [ ] **Unit 1: Add tools to the agent**

**Goal:** Define a set of useful tools and register them on the existing agent

**Requirements:** R1, R3

**Dependencies:** None

**Files:**
- Modify: `src/agent.py` — Add tool functions, decorate with `@agent.tool`

**Approach:**

Define 5 tools that cover different shapes:
- **`get_current_time`** — no params, returns formatted datetime string. Tests basic tool invocation.
- **`calculator(expression: str)`** — evaluates a math expression safely, returns result. Tests parameterized tool calling.
- **`word_count(text: str)`** — returns word/char counts. Tests the agent chaining: user asks about text → agent calls tool → agent incorporates result.
- **`roll_dice(sides: int, count: int)`** — returns random dice rolls. Tests multi-param tools and non-deterministic results.
- **`query_mlflow(sql: str)`** — runs a read-only SQL query against `mlflow.db` (SQLite). Returns results as formatted text. The agent can introspect its own traces, experiment counts, run metadata. Tests the self-referential tracing loop: the agent uses a tool to read traces that were created by the agent using the tool. Only `SELECT` statements allowed — rejects anything else.

**Configuration prerequisite:** `query_mlflow` needs MLflow to actually write to `mlflow.db`. If `MLFLOW_TRACKING_URI` is not set in `.env`, MLflow defaults to the filesystem backend (`./mlruns/`). Either set `MLFLOW_TRACKING_URI=sqlite:///mlflow.db` in `.env` (matching the README's `mlflow ui` command), or have the tool detect the configured backend at runtime. The existing `src/agent.py` calls `mlflow.pydantic_ai.autolog()` without setting a tracking URI, so this must be addressed before the tool works.

Each tool uses `@agent.tool` (not `tool_plain`) so the LLM sees typed parameters with docstrings. All tools are plain sync functions — Pydantic AI handles execution.

Tools go at module level in `src/agent.py`, after `agent = _build_agent()`. Each gets a one-line docstring the LLM uses for tool selection.

**Patterns to follow:**
- Pydantic AI `@agent.tool` decorator pattern: decorate a plain function, first param optionally `RunContext[None]`, typed params with defaults, return any serializable value
- Existing `src/agent.py` structure: env loading → model setup → agent → decorated functions

**Test scenarios:**
- Happy path: Agent responds to "what time is it?" by calling `get_current_time` and including the result in its response
- Happy path: Agent responds to "calculate 15 * 37 + 2" by calling `calculator("15 * 37 + 2")` and returning the numeric result
- Happy path: Agent responds to "count the words in: The quick brown fox" by calling `word_count` and reporting counts
- Happy path: Agent responds to "roll 3d20" by calling `roll_dice(sides=20, count=3)` and listing the results
- Happy path: Agent responds to "how many traces are in mlflow?" by calling `query_mlflow("SELECT COUNT(*) FROM traces")` and reporting the count
- Edge case: `query_mlflow` rejects non-SELECT statements ("DROP TABLE traces" → error string)
- Edge case: Calculator handles division by zero gracefully (returns error string, not exception)
- Edge case: Tools with missing or invalid args get sensible defaults or error strings

**Verification:**
- `len(agent._function_tools)` >= 5 after module import
- MLflow trace shows child spans for tool calls when any tool is invoked during a chat
- Streaming chat behavior unchanged — tools run inline, agent streams final response after tool results

**Implementation note:** Tools with required parameters (no defaults) will raise if the LLM omits them — Pydantic AI validates before calling. Give every parameter a sensible default, or handle `TypeError`/`ValidationError` in a wrapper that returns an error string. The agent should never crash on a malformed tool call.

---

- [ ] **Unit 2: Verify tracing output**

**Goal:** Confirm MLflow captures tool invocations as distinct spans in the trace

**Requirements:** R2, R4

**Dependencies:** Unit 1

**Files:**
- Modify: `src/agent.py` — Add `@mlflow.trace` on each tool function (if not auto-captured by autolog)
- Test: (manual) `mlflow ui` trace inspection

**Approach:**
- Pydantic AI's `instrument=True` on the Agent already tells MLflow to trace agent runs. Tools called during a run should appear as child spans automatically via `mlflow.pydantic_ai.autolog()`.
- If tool spans don't appear in the trace, add `@mlflow.trace(name="tool: {name}", span_type="TOOL")` to each tool function as an explicit fallback.
- Keep the existing `@mlflow.trace(name="kAIusbot chat", span_type="AGENT")` on `stream_response` — tool spans nest under it.

**Test scenarios:**
- Happy path: Ask agent to use a tool → `mlflow ui` trace shows the AGENT span containing TOOL child spans
- Happy path: Each tool span includes input parameters and return value in its attributes
- Happy path: Chat without tool use still produces a clean single-span trace (no regression)

**Verification:**
- Start a chat, trigger at least one tool call, open `mlflow ui --backend-store-uri sqlite:///mlflow.db`
- Trace view shows hierarchical spans: AGENT → TOOL with inputs/outputs visible

## System-Wide Impact

- **Interaction graph:** `main.py` → `stream_response()` → agent (with tools now registered). Tool execution is internal to the agent run. No UI changes.
- **Error propagation:** Tool failures (e.g., malformed calculator input) should return error strings, not raise exceptions that break the streaming loop
- **Unchanged invariants:** `stream_response()` signature unchanged; `clear_chat_history()` untouched; Streamlit session state format unchanged
- **Integration coverage:** The full chain `user input → LLM → tool call → LLM → streamed response` is exercised by any tool-using chat turn

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| `calculator` using `eval()` is unsafe | Use a safe expression evaluator (e.g., `ast.parse` with whitelisted node types). `eval()` on arbitrary LLM output is a code execution risk |
| `query_mlflow` SQL injection via LLM-generated SQL | Reject any statement that isn't `SELECT`. Use a read-only SQLite connection (`mode=ro` via URI). The tool runs locally against a local DB — not a production risk, but still worth the guard |
| `query_mlflow` finds no data because MLflow writes to `./mlruns` not `mlflow.db` | Set `MLFLOW_TRACKING_URI=sqlite:///mlflow.db` in `.env` before running. The autolog tracer and the SQL tool must point at the same backend |
| Tool calls add latency | Tools are all CPU-trivial (<1ms). No noticeable impact on streaming UX |
| LLM may hallucinate tool results instead of calling tools | Tune tool docstrings to be clear and specific. If persistent, adjust the system prompt to prefer tool use |

## Sources & References

- [Pydantic AI Function Tools](https://ai.pydantic.dev/tools/) — `@agent.tool` decorator, `RunContext`, return types
- [MLflow Pydantic AI Tracing](https://mlflow.org/docs/latest/llms/pydantic-ai/index.html) — autolog coverage
- Related code: `src/agent.py` lines 34–57 (agent instantiation and stream_response)
