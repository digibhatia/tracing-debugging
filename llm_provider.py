
"""OpenAI-only chat wrapper, instrumented with a model-call span per request."""

import os
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

from otel_setup import get_tracer
from genai_conventions import (
    GEN_AI_SYSTEM,
    GEN_AI_OPERATION_NAME,
    GEN_AI_REQUEST_MODEL,
    GEN_AI_REQUEST_TEMPERATURE,
    GEN_AI_RESPONSE_MODEL,
    GEN_AI_RESPONSE_FINISH_REASONS,
    GEN_AI_USAGE_INPUT_TOKENS,
    GEN_AI_USAGE_OUTPUT_TOKENS,
    LAB_COST_USD,
    safe_prompt_attribute,
)
from pricing import estimate_cost_usd


# Load .env from the directory containing this file.
ENV_FILE = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_FILE)

DEFAULT_MODEL = "gpt-4o-mini"
_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    """Create and cache the OpenAI client."""
    global _client

    if _client is None:
        api_key = os.environ.get("OPENAI_API_KEY")

        if not api_key:
            raise RuntimeError(
                f"OPENAI_API_KEY is not set. Check your .env file at: {ENV_FILE}"
            )

        _client = OpenAI(api_key=api_key)

    return _client


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class AgentTurn:
    content: Optional[str]
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = ""
    duration_ms: float = 0.0
    raw: object = None


def chat_raw(
    messages,
    tools=None,
    model: str = DEFAULT_MODEL,
    temperature: Optional[float] = None,
    capture_prompt_attrs: bool = True,
) -> AgentTurn:
    """Call the OpenAI chat completion API and record an OpenTelemetry span."""

    tracer = get_tracer("nidan.model")
    client = _get_client()

    with tracer.start_as_current_span("model_call") as span:
        span.set_attribute(GEN_AI_SYSTEM, "openai")
        span.set_attribute(GEN_AI_OPERATION_NAME, "chat")
        span.set_attribute(GEN_AI_REQUEST_MODEL, model)

        if temperature is not None:
            span.set_attribute(GEN_AI_REQUEST_TEMPERATURE, temperature)

        if capture_prompt_attrs and messages:
            last_user = next(
                (
                    message.get("content", "")
                    for message in reversed(messages)
                    if message.get("role") == "user"
                ),
                "",
            )

            span.set_attribute(
                "gen_ai.prompt.last_user_message",
                safe_prompt_attribute(last_user),
            )

        kwargs = {
            "model": model,
            "messages": messages,
        }

        if tools:
            kwargs["tools"] = tools

        if temperature is not None:
            kwargs["temperature"] = temperature

        start_time = time.perf_counter()
        response = client.chat.completions.create(**kwargs)
        duration_ms = (time.perf_counter() - start_time) * 1000

        choice = response.choices[0]
        finish_reason = choice.finish_reason

        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        output_tokens = getattr(usage, "completion_tokens", 0) if usage else 0

        cost = estimate_cost_usd(
            model,
            input_tokens,
            output_tokens,
        )

        span.set_attribute(GEN_AI_RESPONSE_MODEL, response.model)
        span.set_attribute(GEN_AI_RESPONSE_FINISH_REASONS, [finish_reason])
        span.set_attribute(GEN_AI_USAGE_INPUT_TOKENS, input_tokens)
        span.set_attribute(GEN_AI_USAGE_OUTPUT_TOKENS, output_tokens)
        span.set_attribute(LAB_COST_USD, cost)

        tool_calls = []

        for tool_call in (choice.message.tool_calls or []):
            tool_calls.append(
                ToolCall(
                    id=tool_call.id,
                    name=tool_call.function.name,
                    arguments=tool_call.function.arguments,
                )
            )

        return AgentTurn(
            content=choice.message.content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            duration_ms=duration_ms,
            raw=response,
        )
