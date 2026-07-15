import ast
import operator
import os
import sqlite3
from datetime import datetime
from random import randint

import mlflow
from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelRequest,
    ModelResponse,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    ThinkingPart,
    ThinkingPartDelta,
    UserPromptPart,
)
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from src.retrieval import index as retrieval_index
from src.retrieval import store as retrieval_store
from src.retrieval.embedder import embed_query

load_dotenv()

mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "sqlite:///mlflow.db"))
mlflow.pydantic_ai.autolog()

with open("src/prompts/system.md", encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read()

_agent = None
_agent_config = None


def _get_agent(model_name: str | None = None, base_url: str | None = None):
    """Lazily build or rebuild the agent when config changes."""
    global _agent, _agent_config
    model_name = model_name or os.getenv("OLLAMA_MODEL", "gpt-oss:20b")
    base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    key = (model_name, base_url)
    if _agent is None or _agent_config != key:
        model = OpenAIChatModel(
            model_name,
            provider=OpenAIProvider(base_url=base_url, api_key="openai"),
        )
        _agent = Agent(
            model,
            system_prompt=SYSTEM_PROMPT,
            instrument=True,
            tools=[
                get_current_time,
                calculator,
                word_count,
                roll_dice,
                query_mlflow,
                retrieve_docs,
            ],
        )
        _agent_config = key
    return _agent


def _to_messages(history: list[dict]) -> list[ModelRequest | ModelResponse]:
    messages: list[ModelRequest | ModelResponse] = []
    for msg in history:
        if msg["role"] == "user":
            messages.append(ModelRequest(parts=[UserPromptPart(content=msg["content"])]))
        elif msg["role"] == "assistant":
            messages.append(ModelResponse(parts=[TextPart(content=msg["content"])]))
    return messages


# -- tools --

def get_current_time() -> str:
    """Return the current date and time."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}


def _safe_eval(node: ast.AST) -> float:
    match node:
        case ast.Expression(body=body):
            return _safe_eval(body)
        case ast.Constant(value=int() | float()):
            return float(node.value)
        case ast.UnaryOp(op=ast.USub(), operand=operand):
            return -_safe_eval(operand)
        case ast.BinOp(left=left, op=op, right=right):
            op_type = type(op)
            if op_type not in _SAFE_OPS:
                raise ValueError(f"Unsupported operator: {type(op).__name__}")
            return _SAFE_OPS[op_type](_safe_eval(left), _safe_eval(right))
        case _:
            raise ValueError(f"Unsupported expression: {type(node).__name__}")


def calculator(ctx: RunContext[None], expression: str = "") -> str:
    """Evaluate a math expression safely. Supports +, -, *, /, **, and parentheses."""
    if not expression.strip():
        return "Error: empty expression"
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        return str(_safe_eval(tree))
    except ZeroDivisionError:
        return "Error: division by zero"
    except (ValueError, SyntaxError) as e:
        return f"Error: {e}"


def word_count(ctx: RunContext[None], text: str = "") -> str:
    """Count words, characters, and lines in the given text."""
    if not text:
        return "Words: 0, Characters: 0, Lines: 0"
    return f"Words: {len(text.split())}, Characters: {len(text)}, Lines: {text.count(chr(10)) + 1}"


def roll_dice(ctx: RunContext[None], sides: int = 6, count: int = 1) -> str:
    """Roll dice. sides: number of faces per die (default 6), count: number of dice (default 1)."""
    if sides < 2:
        return "Error: dice must have at least 2 sides"
    if count < 1 or count > 100:
        return "Error: count must be between 1 and 100"
    rolls = [randint(1, sides) for _ in range(count)]
    if count == 1:
        return str(rolls[0])
    return f"Rolls: {rolls}, Total: {sum(rolls)}"


def query_mlflow(ctx: RunContext[None], sql: str = "") -> str:
    """Run a read-only SQL query against the MLflow tracking database (SQLite)."""
    if not sql.strip():
        return "Error: empty query"
    if not sql.strip().upper().startswith("SELECT"):
        return "Error: only SELECT queries are allowed"

    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "sqlite:///mlflow.db")
    if not tracking_uri.startswith("sqlite:///"):
        return "Error: MLflow is not using a SQLite backend"

    db_path = tracking_uri.removeprefix("sqlite:///")
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = conn.execute(sql)
        rows = cur.fetchall()
        if not rows:
            return "(no results)"
        col_names = [d[0] for d in cur.description] if cur.description else []
        lines = [", ".join(col_names)] if col_names else []
        lines.append("-" * (len(lines[0]) if lines else 20))
        for row in rows[:50]:
            lines.append(", ".join(str(v) for v in row))
        if len(rows) > 50:
            lines.append(f"... and {len(rows) - 50} more rows")
        conn.close()
        return "\n".join(lines)
    except sqlite3.OperationalError as e:
        return f"Error: {e}"


def retrieve_docs(ctx: RunContext[None], query: str = "", top_k: int = 0) -> str:
    """Search the local project documentation (docs/) for text relevant to a natural-language query.

    Use this to look up background, decisions, or context from the project's own markdown docs
    (plans, summaries) rather than relying on memory. Not connected to the internet.
    """
    if not query.strip():
        return "Error: empty query"
    if top_k < 1:
        top_k = _retrieval_top_k

    try:
        conn = retrieval_store.connect()
        try:
            faiss_index = retrieval_index.get_cached_index(conn)
            if faiss_index is None:
                return "No documents have been indexed yet. Run scripts/ingest.py to build the index."

            query_vec = embed_query(query)
            ids = retrieval_index.search(faiss_index, query_vec, top_k=top_k)
            if not ids:
                return "No relevant documents found."

            results = retrieval_store.fetch_by_ids(conn, ids)
            if not results:
                return "No relevant documents found."

            lines = []
            for i, result in enumerate(results, start=1):
                lines.append(f"{i}. [{result['source_path']}] {result['text']}")
            return "\n\n".join(lines)
        finally:
            conn.close()
    except Exception as e:
        return f"Error: {e}"


_retrieval_top_k = 3


def set_retrieval_top_k(k: int) -> None:
    global _retrieval_top_k
    _retrieval_top_k = k


async def stream_response(
    user_input: str,
    message_history: list[dict],
    model_name: str | None = None,
    base_url: str | None = None,
    temperature: float | None = None,
):
    """Yield structured events from the agent's streaming response."""
    agent = _get_agent(model_name, base_url)
    messages = _to_messages(message_history)
    model_settings = {"temperature": temperature} if temperature is not None else None
    async with agent.run_stream_events(
        user_input, message_history=messages, model_settings=model_settings
    ) as stream:
        async for event in stream:
            match event:
                case PartStartEvent(part=ThinkingPart()):
                    pass  # skip model thinking — not for user display
                case PartStartEvent(part=TextPart()):
                    yield {"type": "text", "delta": event.part.content}
                case PartDeltaEvent(delta=ThinkingPartDelta()):
                    pass  # skip model thinking deltas
                case PartDeltaEvent():
                    yield {"type": "text", "delta": event.delta.content_delta}
                case FunctionToolCallEvent():
                    yield {"type": "tool_call", "name": event.part.tool_name}
                case FunctionToolResultEvent():
                    yield {"type": "tool_result", "name": event.part.tool_name}
