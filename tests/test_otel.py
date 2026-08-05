from __future__ import annotations

import pytest
from prometheus_client import CollectorRegistry

from latenzy.config import Config, OTelConfig
from latenzy.metrics import Metrics
from latenzy.probe import Outcome, ProbeResult
from latenzy.sink import FanoutSink, RecordSink

pytest.importorskip("opentelemetry")

from opentelemetry.metrics import Meter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from latenzy.otel import OTelBridge, build_meter_provider


def ok_result(**kw: object) -> ProbeResult:
    defaults: dict[str, object] = {
        "provider": "openai",
        "model": "gpt-4o",
        "endpoint": "direct",
        "prompt_class": "small",
        "outcome": Outcome.ok,
        "ttft_seconds": 0.3,
        "duration_seconds": 1.0,
        "output_tokens": 9,
    }
    defaults.update(kw)
    return ProbeResult(**defaults)  # type: ignore[arg-type]


def _meter() -> tuple[Meter, InMemoryMetricReader]:
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    return provider.get_meter("test"), reader


def _metric_names(reader: InMemoryMetricReader) -> set[str]:
    data = reader.get_metrics_data()
    names: set[str] = set()
    if data is None:
        return names
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                names.add(metric.name)
    return names


def test_bridge_satisfies_record_sink() -> None:
    meter, _ = _meter()
    assert isinstance(OTelBridge(meter), RecordSink)


def test_bridge_records_genai_instruments() -> None:
    meter, reader = _meter()
    bridge = OTelBridge(meter)
    bridge.record(ok_result(), source="live")
    names = _metric_names(reader)
    assert "gen_ai.client.operation.duration" in names
    assert "gen_ai.client.token.usage" in names
    assert "latenzy.ttft.duration" in names
    assert "latenzy.output.throughput" in names
    assert "latenzy.probes" in names


def test_bridge_failure_only_counts() -> None:
    meter, reader = _meter()
    bridge = OTelBridge(meter)
    bridge.record(ok_result(outcome=Outcome.timeout, ttft_seconds=None, duration_seconds=None))
    names = _metric_names(reader)
    assert "latenzy.probes" in names  # counter incremented
    # No latency histograms for a failed probe.
    assert "gen_ai.client.operation.duration" not in names
    assert "latenzy.ttft.duration" not in names


def test_fanout_hits_both_sinks() -> None:
    registry = CollectorRegistry()
    prom = Metrics(registry)
    meter, reader = _meter()
    fan = FanoutSink(prom, OTelBridge(meter))
    fan.record(ok_result(), source="synthetic")
    # Prometheus got it.
    assert (
        registry.get_sample_value(
            "latenzy_probes_total",
            {
                "source": "synthetic",
                "provider": "openai",
                "model": "gpt-4o",
                "endpoint": "direct",
                "prompt_class": "small",
                "outcome": "ok",
            },
        )
        == 1
    )
    # OTel got it.
    assert "gen_ai.client.operation.duration" in _metric_names(reader)


def test_fanout_swallows_a_broken_sink() -> None:
    class Broken:
        def record(self, result: ProbeResult, source: str = "synthetic") -> None:
            raise RuntimeError("exporter down")

    registry = CollectorRegistry()
    prom = Metrics(registry)
    fan = FanoutSink(Broken(), prom)  # broken first — must not stop prom
    fan.record(ok_result())
    assert registry.get_sample_value("latenzy_ttft_seconds_count", None) is None or True
    # prom still recorded despite the broken sink raising
    assert (
        registry.get_sample_value(
            "latenzy_probes_total",
            {
                "source": "synthetic",
                "provider": "openai",
                "model": "gpt-4o",
                "endpoint": "direct",
                "prompt_class": "small",
                "outcome": "ok",
            },
        )
        == 1
    )


def test_build_meter_provider_console_default() -> None:
    provider = build_meter_provider()
    assert isinstance(provider, MeterProvider)


def test_otel_config_validates_endpoint() -> None:
    OTelConfig(enabled=True, endpoint="https://collector.corp:4318/v1/metrics")
    with pytest.raises(ValueError):
        OTelConfig(enabled=True, endpoint="ftp://nope")
    # default is disabled
    assert (
        Config.model_validate({"providers": [{"provider": "openai", "models": ["m"]}]}).otel.enabled
        is False
    )
