# MLflow tracing with Pydantic AI + Ollama

**Date:** 2026-07-13
**MLflow:** 3.14.0
**Pydantic AI:** 1.107.1

## What works

`mlflow.pydantic_ai.autolog()` traces Pydantic AI agent calls when:
- Running Pydantic AI **1.x** (2.x removed `instrument=True`, which autolog depends on)
- Using a provider that routes through `InstrumentedModel` (OpenAI, Anthropic, Bedrock)
- `instrument=True` is passed to the Agent

```python
import mlflow
mlflow.pydantic_ai.autolog()

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

model = OpenAIChatModel(
    "llama3.1",
    provider=OpenAIProvider(base_url="http://localhost:11434/v1", api_key="ollama"),
)
agent = Agent(model, system_prompt="...", instrument=True)
```

Result: 2 nested spans per request:
```
@mlflow.trace wrapper     ← user_input, message_history
  └── Agent.run_stream    ← full prompt, system_prompt
```

## What doesn't work

| Approach | Issue |
|----------|-------|
| `mlflow.pydantic_ai.autolog()` + Pydantic AI **2.x** | `instrument=True` removed from Agent.__init__; `InstrumentedModel` not used internally |
| `mlflow.pydantic_ai.autolog()` + `OllamaModel` | Ollama provider doesn't route through `InstrumentedModel` — autolog patches never fire |
| `mlflow.start_span()` as root | Orphaned — needs a parent trace from `@mlflow.trace` or similar |
| Logfire | Paid product |

## Key insight

The trick is using `OpenAIChatModel` pointed at Ollama's OpenAI-compatible endpoint. Same local `llama3.1`, same `ollama serve`, but Pydantic AI treats it as an OpenAI model → `InstrumentedModel` path → autolog works.

## System prompt quirk

`llama3.1` doesn't respect the OpenAI `system` role well. The system prompt is embedded inline as `"system: ..."` at the start of the user message — the same pattern the original LangChain version used. It's also set on the Agent (`system_prompt=`) so autolog captures it in trace attributes.
