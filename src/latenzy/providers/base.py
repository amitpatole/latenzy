"""Shared streaming-probe flow. Each provider supplies the request shape and an
SSE line parser; the base class owns timing, outcome classification, and the
guarantee that API keys never appear in results, exceptions we raise, or logs."""

from __future__ import annotations

import asyncio
import json
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, ClassVar

import httpx

from latenzy.config import ProviderConfig
from latenzy.probe import Outcome, ProbeResult

# A probe expects ~16 output tokens; these caps are orders of magnitude above
# any honest response and bound what a hostile endpoint can make us buffer.
MAX_LINE_BYTES = 512 * 1024
MAX_STREAM_BYTES = 8 * 1024 * 1024
# json.loads recurses on nested structures and raises RecursionError (not a
# JSONDecodeError) on deep input; cap depth so a hostile payload can't. Honest
# SSE deltas are shallow (a handful of levels).
MAX_JSON_DEPTH = 32
# Reported token counts above this are treated as absent — a hostile endpoint
# could otherwise send an integer so large the tokens/sec division overflows
# float, or a merely-huge one that poisons the throughput histogram sum.
MAX_REPORTED_TOKENS = 10_000_000


class StreamLimitExceeded(Exception):
    pass


def sane_token_count(value: object) -> int | None:
    """Accept a provider-reported output-token count only if it is a plausible
    non-negative integer; reject bools, wrong types, and absurd magnitudes."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < 0 or value > MAX_REPORTED_TOKENS:
        return None
    return value


def _depth_limited(raw: str) -> Any:
    """json.loads with a bounded nesting depth (RecursionError-safe)."""

    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        return dict(pairs)

    decoder = json.JSONDecoder(object_pairs_hook=hook)
    # Cheap structural depth check before decoding — bounds recursion without
    # a custom parser.
    depth = 0
    for ch in raw:
        if ch in "[{":
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise ValueError("json nesting too deep")
        elif ch in "]}":
            depth -= 1
    return decoder.decode(raw)


async def _iter_sse_lines(response: httpx.Response) -> AsyncIterator[str]:
    """Split SSE lines with hard byte bounds — aiter_lines() would buffer a
    newline-free stream without limit."""
    buffer = b""
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > MAX_STREAM_BYTES:
            raise StreamLimitExceeded(f"stream exceeded {MAX_STREAM_BYTES} bytes")
        buffer += chunk
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            yield line.decode("utf-8", "replace").rstrip("\r")
        if len(buffer) > MAX_LINE_BYTES:
            raise StreamLimitExceeded(f"line exceeded {MAX_LINE_BYTES} bytes")


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

        async def consume() -> Outcome | None:
            nonlocal ttft, output_tokens
            async with self._client.stream(
                "POST",
                spec.url,
                headers=spec.headers,
                json=spec.body,
                timeout=timeout,
            ) as response:
                if response.status_code == 429:
                    return Outcome.rate_limited
                if response.status_code != 200:
                    return Outcome.error
                async for line in _iter_sse_lines(response):
                    if not line.startswith("data:"):
                        continue
                    payload = line[len("data:") :].strip()
                    if not payload or payload == "[DONE]":
                        continue
                    try:
                        data = _depth_limited(payload)
                    except (json.JSONDecodeError, ValueError, RecursionError):
                        continue
                    # Every response byte here is attacker-controlled; a
                    # non-dict payload would crash parse_data's .get() calls.
                    if not isinstance(data, dict):
                        continue
                    event = self.parse_data(data)
                    if event.has_token and ttft is None:
                        ttft = time.perf_counter() - start
                    if event.output_tokens is not None:
                        output_tokens = event.output_tokens
            return None

        try:
            # Hard overall deadline: httpx read timeouts are per-chunk, so a
            # slow-drip stream would otherwise hold this probe (and its
            # concurrency slot) open forever.
            early = await asyncio.wait_for(consume(), timeout=timeout)
            if early is not None:
                return result(early)
        except (TimeoutError, asyncio.TimeoutError, httpx.TimeoutException):
            return result(Outcome.timeout)
        except StreamLimitExceeded:
            return result(Outcome.error)
        except httpx.HTTPError:
            return result(Outcome.error)
        except Exception:
            # Fail closed: no malformed byte from a provider endpoint may crash
            # a probe (and, via run_forever, the whole monitor). Defense in
            # depth behind the type guards above.
            return result(Outcome.error)
        duration = time.perf_counter() - start
        if ttft is None:
            # Stream ended without a single token: not a success.
            return result(Outcome.error, duration=duration)
        return result(Outcome.ok, ttft=ttft, duration=duration, tokens=output_tokens)
