"""Shared streaming-probe flow. Each provider supplies the request shape and an
SSE line parser; the base class owns timing, outcome classification, and the
guarantee that API keys never appear in results, exceptions we raise, or logs."""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar

import httpx

from latenzy.config import ProviderConfig
from latenzy.probe import Outcome, ProbeResult


@dataclass(frozen=True)
class RequestSpec:
    url: str
    headers: dict[str, str]
    body: dict[str, Any]


@dataclass(frozen=True)
class StreamEvent:
    """What one SSE data line contributed: token-bearing content and/or a usage total."""

    has_token: bool = False
    output_tokens: int | None = None


class ProviderProbe(ABC):
    name: ClassVar[str]

    def __init__(self, config: ProviderConfig, client: httpx.AsyncClient) -> None:
        self._config = config
        self._client = client

    @abstractmethod
    def build_request(self, model: str, prompt: str, max_output_tokens: int) -> RequestSpec: ...

    @abstractmethod
    def parse_data(self, data: dict[str, Any]) -> StreamEvent:
        """Interpret one parsed SSE `data:` JSON payload."""

    async def probe(
        self,
        model: str,
        prompt_class: str,
        prompt: str,
        max_output_tokens: int,
        timeout: float,
    ) -> ProbeResult:
        spec = self.build_request(model, prompt, max_output_tokens)

        def result(
            outcome: Outcome,
            ttft: float | None = None,
            duration: float | None = None,
            tokens: int | None = None,
        ) -> ProbeResult:
            return ProbeResult(
                provider=self._config.provider.value,
                model=model,
                endpoint=self._config.endpoint,
                prompt_class=prompt_class,
                outcome=outcome,
                ttft_seconds=ttft,
                duration_seconds=duration,
                output_tokens=tokens,
            )

        ttft: float | None = None
        output_tokens: int | None = None
        start = time.perf_counter()
        try:
            async with self._client.stream(
                "POST",
                spec.url,
                headers=spec.headers,
                json=spec.body,
                timeout=timeout,
            ) as response:
                if response.status_code == 429:
                    return result(Outcome.rate_limited)
                if response.status_code != 200:
                    return result(Outcome.error)
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[len("data:") :].strip()
                    if not payload or payload == "[DONE]":
                        continue
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    event = self.parse_data(data)
                    if event.has_token and ttft is None:
                        ttft = time.perf_counter() - start
                    if event.output_tokens is not None:
                        output_tokens = event.output_tokens
        except httpx.TimeoutException:
            return result(Outcome.timeout)
        except httpx.HTTPError:
            return result(Outcome.error)
        duration = time.perf_counter() - start
        if ttft is None:
            # Stream ended without a single token: not a success.
            return result(Outcome.error, duration=duration)
        return result(Outcome.ok, ttft=ttft, duration=duration, tokens=output_tokens)
