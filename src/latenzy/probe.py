"""Probe result types and the deterministic prompt corpus.

Latency scales with input tokens, so probes are labelled by prompt class;
comparing models on unequal prompts is meaningless. Prompts ask for a short
answer so output cost stays bounded regardless of input size.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from latenzy.config import PromptClass


class Outcome(str, enum.Enum):
    ok = "ok"
    rate_limited = "rate_limited"
    timeout = "timeout"
    error = "error"


@dataclass(frozen=True)
class ProbeResult:
    provider: str
    model: str
    endpoint: str
    prompt_class: str
    outcome: Outcome
    ttft_seconds: float | None = None
    duration_seconds: float | None = None
    output_tokens: int | None = None

    @property
    def tokens_per_second(self) -> float | None:
        """Streaming throughput over the generation span (after first token)."""
        if (
            self.outcome is not Outcome.ok
            or self.output_tokens is None
            or self.output_tokens < 2
            or self.ttft_seconds is None
            or self.duration_seconds is None
            or self.duration_seconds <= self.ttft_seconds
        ):
            return None
        return (self.output_tokens - 1) / (self.duration_seconds - self.ttft_seconds)


_QUESTION = "Reply with one short sentence: why does the sky appear blue?"

_FILLER = (
    "The following background text is context you may ignore. "
    "Rayleigh scattering describes how electromagnetic radiation is scattered "
    "by particles much smaller than its wavelength, which in the atmosphere "
    "means shorter blue wavelengths scatter far more than red ones. "
)

PROMPTS: dict[PromptClass, str] = {
    PromptClass.small: _QUESTION,
    PromptClass.medium: _FILLER * 8 + _QUESTION,
    PromptClass.large: _FILLER * 80 + _QUESTION,
}
