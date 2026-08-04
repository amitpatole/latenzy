"""Prometheus metrics. Histograms are only observed for successful probes so
error runs don't skew latency percentiles; failures land in the outcome counter."""

from __future__ import annotations

import time

from prometheus_client import Counter, Gauge, Histogram
from prometheus_client.registry import REGISTRY, CollectorRegistry

from latenzy.probe import Outcome, ProbeResult

LABELS = ("provider", "model", "endpoint", "prompt_class")

TTFT_BUCKETS = (0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0, 1.5, 2.5, 4.0, 6.0, 10.0, 20.0, 30.0)
DURATION_BUCKETS = (0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 15.0, 30.0, 60.0, 120.0)
TPS_BUCKETS = (1.0, 5.0, 10.0, 20.0, 40.0, 60.0, 90.0, 120.0, 180.0, 300.0)


class Metrics:
    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        reg = registry if registry is not None else REGISTRY
        self.registry = reg
        self.ttft = Histogram(
            "latenzy_ttft_seconds",
            "Time to first streamed token, successful probes only.",
            LABELS,
            buckets=TTFT_BUCKETS,
            registry=reg,
        )
        self.duration = Histogram(
            "latenzy_request_duration_seconds",
            "Total request duration, successful probes only.",
            LABELS,
            buckets=DURATION_BUCKETS,
            registry=reg,
        )
        self.tokens_per_second = Histogram(
            "latenzy_output_tokens_per_second",
            "Streaming throughput over the generation span, successful probes only.",
            LABELS,
            buckets=TPS_BUCKETS,
            registry=reg,
        )
        self.probes = Counter(
            "latenzy_probes_total",
            "Probe attempts by outcome (ok, rate_limited, timeout, error).",
            (*LABELS, "outcome"),
            registry=reg,
        )
        self.last_success = Gauge(
            "latenzy_last_success_timestamp_seconds",
            "Unix time of the last successful probe; alert on staleness.",
            LABELS,
            registry=reg,
        )

    def record(self, result: ProbeResult) -> None:
        labels = (result.provider, result.model, result.endpoint, result.prompt_class)
        self.probes.labels(*labels, result.outcome.value).inc()
        if result.outcome is not Outcome.ok:
            return
        if result.ttft_seconds is not None:
            self.ttft.labels(*labels).observe(result.ttft_seconds)
        if result.duration_seconds is not None:
            self.duration.labels(*labels).observe(result.duration_seconds)
        tps = result.tokens_per_second
        if tps is not None:
            self.tokens_per_second.labels(*labels).observe(tps)
        self.last_success.labels(*labels).set(time.time())
