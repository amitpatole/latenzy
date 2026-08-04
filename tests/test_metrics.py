from __future__ import annotations

from prometheus_client import CollectorRegistry

from latenzy.metrics import Metrics
from latenzy.probe import Outcome, ProbeResult


def result(outcome: Outcome = Outcome.ok, **kw: object) -> ProbeResult:
    defaults: dict[str, object] = {
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
        "endpoint": "direct",
        "prompt_class": "small",
        "outcome": outcome,
        "ttft_seconds": 0.4,
        "duration_seconds": 1.2,
        "output_tokens": 9,
    }
    defaults.update(kw)
    return ProbeResult(**defaults)  # type: ignore[arg-type]


LABELS = {
    "source": "synthetic",
    "provider": "anthropic",
    "model": "claude-sonnet-4-6",
    "endpoint": "direct",
    "prompt_class": "small",
}


def test_success_observes_histograms(registry: CollectorRegistry, metrics: Metrics) -> None:
    metrics.record(result())
    assert registry.get_sample_value("latenzy_ttft_seconds_count", LABELS) == 1
    assert registry.get_sample_value("latenzy_ttft_seconds_sum", LABELS) == 0.4
    assert registry.get_sample_value("latenzy_request_duration_seconds_sum", LABELS) == 1.2
    assert registry.get_sample_value("latenzy_probes_total", {**LABELS, "outcome": "ok"}) == 1
    assert registry.get_sample_value("latenzy_last_success_timestamp_seconds", LABELS) is not None
    # (9 - 1) tokens over (1.2 - 0.4)s of generation = 10 tok/s
    assert registry.get_sample_value("latenzy_output_tokens_per_second_sum", LABELS) == 10.0


def test_failures_count_but_do_not_skew_latency(
    registry: CollectorRegistry, metrics: Metrics
) -> None:
    metrics.record(result(Outcome.rate_limited, ttft_seconds=None, duration_seconds=None))
    metrics.record(result(Outcome.timeout, ttft_seconds=None, duration_seconds=None))
    assert (
        registry.get_sample_value("latenzy_probes_total", {**LABELS, "outcome": "rate_limited"})
        == 1
    )
    assert registry.get_sample_value("latenzy_probes_total", {**LABELS, "outcome": "timeout"}) == 1
    assert registry.get_sample_value("latenzy_ttft_seconds_count", LABELS) is None
    assert registry.get_sample_value("latenzy_last_success_timestamp_seconds", LABELS) is None


def test_tokens_per_second_guards() -> None:
    assert result(output_tokens=1).tokens_per_second is None
    assert result(duration_seconds=0.4).tokens_per_second is None  # equal to ttft
    assert result(Outcome.error).tokens_per_second is None
