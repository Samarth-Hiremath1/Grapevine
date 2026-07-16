"""Provider-agnostic async LLM client with retry/backoff and cost tracking.

The rollout engine only depends on the small :class:`LLMClient` interface, so
the same conversation code drives an OpenAI-compatible HTTP endpoint, the
Anthropic Messages API, a locally hosted model, or a deterministic scripted stub
in tests. Every client reports token usage and an estimated USD cost per call,
which the engine accumulates per run.
"""

from __future__ import annotations

import asyncio
import os
import random
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class Message:
    """A single chat message."""

    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class Completion:
    """The result of one model call, including usage and estimated cost."""

    text: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float


@dataclass
class Pricing:
    """USD price per 1K tokens for a model."""

    input_per_1k: float
    output_per_1k: float

    def cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimated USD cost for the given token counts."""
        return (
            prompt_tokens / 1000.0 * self.input_per_1k
            + completion_tokens / 1000.0 * self.output_per_1k
        )


# Published list prices (USD / 1K tokens) for a few inexpensive models, current
# as of mid-2026. Used only to estimate run cost; override via Pricing if stale.
DEFAULT_PRICING: dict[str, Pricing] = {
    "gpt-4o-mini": Pricing(0.00015, 0.0006),
    "gpt-4.1-mini": Pricing(0.0004, 0.0016),
    "gpt-4.1-nano": Pricing(0.0001, 0.0004),
    "claude-3-5-haiku-latest": Pricing(0.0008, 0.004),
    "claude-3-5-haiku-20241022": Pricing(0.0008, 0.004),
}


def pricing_for(model: str) -> Pricing:
    """Return known pricing for ``model``, or a zero-cost fallback if unknown."""
    return DEFAULT_PRICING.get(model, Pricing(0.0, 0.0))


@dataclass
class RetryConfig:
    """Exponential-backoff retry policy for transient API failures."""

    max_retries: int = 5
    base_delay: float = 0.5
    max_delay: float = 20.0
    jitter: float = 0.3


class LLMClient(ABC):
    """Abstract async chat client that tracks cumulative token usage and cost."""

    def __init__(self, model: str) -> None:
        self.model = model
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_cost_usd = 0.0
        self.n_calls = 0

    def _record(self, completion: Completion) -> None:
        self.total_prompt_tokens += completion.prompt_tokens
        self.total_completion_tokens += completion.completion_tokens
        self.total_cost_usd += completion.cost_usd
        self.n_calls += 1

    @abstractmethod
    async def complete(
        self, messages: list[Message], *, max_tokens: int = 512, temperature: float = 0.7
    ) -> Completion:
        """Return a completion for ``messages``. Implementations record usage."""
        raise NotImplementedError

    def usage(self) -> dict[str, float]:
        """Return a snapshot of cumulative usage and cost."""
        return {
            "n_calls": float(self.n_calls),
            "prompt_tokens": float(self.total_prompt_tokens),
            "completion_tokens": float(self.total_completion_tokens),
            "cost_usd": self.total_cost_usd,
        }


async def _with_retry(
    coro_factory: Callable[[], Awaitable[httpx.Response]],
    retry: RetryConfig,
    rng: random.Random,
) -> httpx.Response:
    """Call an async request factory with exponential backoff on transient errors."""
    last_exc: Exception | None = None
    for attempt in range(retry.max_retries + 1):
        try:
            response: httpx.Response = await coro_factory()
            if response.status_code in (429, 500, 502, 503, 504):
                raise httpx.HTTPStatusError(
                    f"retryable status {response.status_code}",
                    request=response.request,
                    response=response,
                )
            return response
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            last_exc = exc
            if attempt >= retry.max_retries:
                break
            delay = min(retry.max_delay, retry.base_delay * (2**attempt))
            delay += rng.uniform(0, retry.jitter * delay)
            await asyncio.sleep(delay)
    assert last_exc is not None
    raise last_exc


class OpenAICompatibleClient(LLMClient):
    """Async client for any OpenAI-compatible ``/chat/completions`` endpoint.

    Works with the OpenAI API, and with OpenAI-compatible gateways (Together,
    Groq, Fireworks, a local vLLM/Ollama server, ...). Credentials and base URL
    are read from arguments or environment variables.
    """

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        pricing: Pricing | None = None,
        retry: RetryConfig | None = None,
        timeout: float = 60.0,
        seed: int = 0,
    ) -> None:
        super().__init__(model)
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.pricing = pricing or pricing_for(model)
        self.retry = retry or RetryConfig()
        self.timeout = timeout
        self._rng = random.Random(seed)

    async def complete(
        self, messages: list[Message], *, max_tokens: int = 512, temperature: float = 0.7
    ) -> Completion:
        """POST a chat completion request and return the parsed result."""
        if not self.api_key:
            raise RuntimeError(
                "No API key set. Provide api_key= or set OPENAI_API_KEY (or use a "
                "ScriptedClient/LocalHFClient for offline runs)."
            )
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}

        async with httpx.AsyncClient(timeout=self.timeout) as http:

            async def _do() -> httpx.Response:
                return await http.post(
                    f"{self.base_url}/chat/completions", json=payload, headers=headers
                )

            response = await _with_retry(_do, self.retry, self._rng)
        response.raise_for_status()
        data = response.json()
        text = data["choices"][0]["message"]["content"] or ""
        usage = data.get("usage", {})
        prompt_tokens = int(usage.get("prompt_tokens", 0))
        completion_tokens = int(usage.get("completion_tokens", 0))
        completion = Completion(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=self.pricing.cost(prompt_tokens, completion_tokens),
        )
        self._record(completion)
        return completion


class AnthropicClient(LLMClient):
    """Async client for the Anthropic Messages API (system prompt handled apart)."""

    def __init__(
        self,
        model: str = "claude-3-5-haiku-latest",
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        pricing: Pricing | None = None,
        retry: RetryConfig | None = None,
        timeout: float = 60.0,
        seed: int = 0,
    ) -> None:
        super().__init__(model)
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.base_url = (base_url or "https://api.anthropic.com/v1").rstrip("/")
        self.pricing = pricing or pricing_for(model)
        self.retry = retry or RetryConfig()
        self.timeout = timeout
        self._rng = random.Random(seed)

    async def complete(
        self, messages: list[Message], *, max_tokens: int = 512, temperature: float = 0.7
    ) -> Completion:
        """POST to the Anthropic Messages API and return the parsed result."""
        if not self.api_key:
            raise RuntimeError(
                "No API key set. Provide api_key= or set ANTHROPIC_API_KEY."
            )
        system = "\n".join(m.content for m in messages if m.role == "system")
        convo = [
            {"role": m.role, "content": m.content} for m in messages if m.role != "system"
        ]
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": convo,
        }
        if system:
            payload["system"] = system
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as http:

            async def _do() -> httpx.Response:
                return await http.post(f"{self.base_url}/messages", json=payload, headers=headers)

            response = await _with_retry(_do, self.retry, self._rng)
        response.raise_for_status()
        data = response.json()
        text = "".join(block.get("text", "") for block in data.get("content", []))
        usage = data.get("usage", {})
        prompt_tokens = int(usage.get("input_tokens", 0))
        completion_tokens = int(usage.get("output_tokens", 0))
        completion = Completion(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=self.pricing.cost(prompt_tokens, completion_tokens),
        )
        self._record(completion)
        return completion


class ScriptedClient(LLMClient):
    """Deterministic offline client for tests and diagnostics.

    Instead of calling a network API, it delegates to a user-supplied
    ``responder`` callable that maps ``(messages) -> str``. Token counts are
    estimated by whitespace word count so cost accounting can still be exercised.
    """

    def __init__(
        self,
        responder: Callable[[list[Message]], str],
        *,
        model: str = "scripted",
        price: Pricing | None = None,
    ) -> None:
        super().__init__(model)
        self.responder = responder
        self.price = price or Pricing(0.0, 0.0)

    async def complete(
        self, messages: list[Message], *, max_tokens: int = 512, temperature: float = 0.7
    ) -> Completion:
        """Return the scripted response for ``messages``."""
        text = self.responder(messages)
        prompt_tokens = sum(len(m.content.split()) for m in messages)
        completion_tokens = len(text.split())
        completion = Completion(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=self.price.cost(prompt_tokens, completion_tokens),
        )
        self._record(completion)
        return completion
