"""Request-scoped LLM token usage tracking.

Goal:
- Track input/output/total tokens across all Azure OpenAI calls in a request.
- Persist usage only in export artifacts (Cosmos documents / report JSON/PDF),
  not in end-user API responses.

Implementation approach:
- Use contextvars so nested calls (and asyncio.to_thread) can accumulate safely.
- The Azure OpenAI wrapper records usage on successful responses.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.config import settings


@dataclass
class TokenUsageAccumulator:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    calls: List[Dict[str, Any]] = field(default_factory=list)

    def add(
        self,
        *,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        model: Optional[str] = None,
    ) -> None:
        self.input_tokens += max(0, int(input_tokens))
        self.output_tokens += max(0, int(output_tokens))
        self.total_tokens += max(0, int(total_tokens))

        self.calls.append(
            {
                "model": model,
                "input_tokens": max(0, int(input_tokens)),
                "output_tokens": max(0, int(output_tokens)),
                "total_tokens": max(0, int(total_tokens)),
            }
        )

    def snapshot(self, *, include_calls: bool = False) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "input_tokens": int(self.input_tokens),
            "output_tokens": int(self.output_tokens),
            "total_tokens": int(self.total_tokens),
            "calls_count": int(len(self.calls)),
        }

        # Optional cost computation (only if configured)
        in_price = getattr(settings, "azure_openai_price_per_1k_input_tokens_usd", None)
        out_price = getattr(settings, "azure_openai_price_per_1k_output_tokens_usd", None)
        if isinstance(in_price, (int, float)) and isinstance(out_price, (int, float)):
            data["cost_usd"] = float(
                (self.input_tokens / 1000.0) * float(in_price)
                + (self.output_tokens / 1000.0) * float(out_price)
            )
            data["pricing"] = {
                "price_per_1k_input_tokens_usd": float(in_price),
                "price_per_1k_output_tokens_usd": float(out_price),
            }

        if include_calls:
            data["calls"] = list(self.calls)

        return data


_llm_usage_var: ContextVar[Optional[TokenUsageAccumulator]] = ContextVar(
    "llm_usage_accumulator", default=None
)


def start_request_llm_usage() -> Token:
    """Initialize a fresh accumulator for the current request context."""

    return _llm_usage_var.set(TokenUsageAccumulator())


def end_request_llm_usage(token: Token) -> None:
    """Reset request accumulator back to previous value."""

    _llm_usage_var.reset(token)


def get_llm_usage_accumulator() -> Optional[TokenUsageAccumulator]:
    return _llm_usage_var.get()


def get_llm_usage_snapshot(*, include_calls: bool = False) -> Dict[str, Any]:
    acc = get_llm_usage_accumulator()
    if acc is None:
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "calls_count": 0,
        }
    return acc.snapshot(include_calls=include_calls)


def record_openai_chat_completion_usage(*, response: Any, model: Optional[str]) -> None:
    """Record usage fields from an OpenAI ChatCompletion response.

    Works with azure-openai / openai-python response objects.
    """

    acc = get_llm_usage_accumulator()
    if acc is None:
        return

    usage = getattr(response, "usage", None)
    if not usage:
        return

    input_tokens = getattr(usage, "prompt_tokens", None)
    output_tokens = getattr(usage, "completion_tokens", None)
    total_tokens = getattr(usage, "total_tokens", None)

    if input_tokens is None and output_tokens is None and total_tokens is None:
        return

    acc.add(
        input_tokens=int(input_tokens or 0),
        output_tokens=int(output_tokens or 0),
        total_tokens=int(total_tokens or 0),
        model=model,
    )
