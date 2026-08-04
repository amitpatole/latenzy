"""Passive instrumentation for *real* application traffic.

The prober measures synthetic canaries; this records the latency of an app's
actual LLM calls into the same metric names under ``source="live"``, so one
dashboard shows both. It is framework- and provider-agnostic: the host app
drives a small observation object (mark first token, set token count, set
outcome), and latenzy owns the timing and label validation.

The metric semantics follow the OpenTelemetry GenAI conventions (per-request
TTFT and total duration keyed by request model), so the live series line up
with an OpenTelemetry pipeline; a direct OTel meter bridge is planned.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

from latenzy.config import PromptClass, ensure_metric_label
from latenzy.metrics import LIVE, Metrics
from latenzy.probe import Outcome, ProbeResult
from latenzy.providers.base import sane_token_count

# Prompt-size class boundaries in approximate input tokens, so live traffic
# lands in the same small/medium/large buckets the prober uses.
SMALL_MAX_TOKENS = 200
MEDIUM_MAX_TOKENS = 2000
# Rough chars-per-token when only raw text length is known.
_CHARS_PER_TOKEN = 4


def classify_prompt(*, tokens: int | None = None, text: str | None = None) -> PromptClass:
    """Bucket a prompt into small/medium/large by (approximate) input tokens."""
    if tokens is None:
        if text is None:
            raise ValueError("classify_prompt requires either tokens or text")
        tokens = max(1, len(text) // _CHARS_PER_TOKEN)
    if tokens < 0:
        raise ValueError("tokens must be non-negative")
    if tokens <= SMALL_MAX_TOKENS:
        return PromptClass.small
    if tokens <= MEDIUM_MAX_TOKENS:
        return PromptClass.medium
    return PromptClass.large


class LiveObservation:
    """Handed to the caller inside :meth:`LiveRecorder.observe`. The app calls
    :meth:`first_token` when the first token arrives and sets ``output_tokens``;
    latenzy times the rest and records on context exit."""

    def __init__(self) -> None:
        self._start = time.perf_counter()
        self._ttft: float | None = None
        self.output_tokens: int | None = None
        self.outcome: Outcome = Outcome.ok

    def first_token(self) -> None:
        if self._ttft is None:
            self._ttft = time.perf_counter() - self._start

    def _result(
        self, provider: str, model: str, endpoint: str, prompt_class: PromptClass
    ) -> ProbeResult:
        duration = time.perf_counter() - self._start
        # No token seen on a nominally-ok stream is not a success.
        outcome = self.outcome
        if outcome is Outcome.ok and self._ttft is None:
            outcome = Outcome.error
        # Bound an app-supplied token count the same way the prober bounds a
        # provider-supplied one (avoids tokens/sec overflow and sum poisoning).
        tokens = sane_token_count(self.output_tokens) if outcome is Outcome.ok else None
        return ProbeResult(
            provider=provider,
            model=model,
            endpoint=endpoint,
            prompt_class=prompt_class.value,
            outcome=outcome,
            ttft_seconds=self._ttft,
            duration_seconds=duration,
            output_tokens=tokens,
        )


class LiveRecorder:
    """Records real-traffic latency into a shared :class:`Metrics` instance."""

    def __init__(self, metrics: Metrics) -> None:
        self._metrics = metrics

    @contextmanager
    def observe(
        self,
        *,
        provider: str,
        model: str,
        prompt_class: PromptClass,
        endpoint: str = "live",
    ) -> Iterator[LiveObservation]:
        """Time one live LLM request and record it under ``source="live"``.

        Label values are charset-validated (they may come from user input) so a
        host app cannot explode metric cardinality or inject control chars.
        A raised exception is recorded as an ``error`` outcome and re-raised.
        """
        ensure_metric_label(provider, "provider")
        ensure_metric_label(model, "model")
        ensure_metric_label(endpoint, "endpoint")
        obs = LiveObservation()
        try:
            yield obs
        except Exception:
            obs.outcome = Outcome.error
            raise
        finally:
            result = obs._result(provider, model, endpoint, prompt_class)
            self._metrics.record(result, source=LIVE)


def measure_stream(
    chunks: Iterator[str],
    observation: LiveObservation,
) -> Iterator[str]:
    """Wrap a text-chunk iterator, marking first-token timing as chunks flow.

    Convenience for the common case: ``for c in measure_stream(resp, obs): ...``
    marks ``obs.first_token()`` on the first non-empty chunk.
    """
    for chunk in chunks:
        if chunk:
            observation.first_token()
        yield chunk
