"""OpenTelemetry bridge — mirror latenzy measurements to OTel instruments.

Optional: requires the ``otel`` extra (``pip install 'latenzy[otel]'``). The
heavy OpenTelemetry packages are imported lazily so the base wheel stays light
and importing ``latenzy`` never pulls them in.

Instrument names follow the OpenTelemetry GenAI semantic conventions where they
exist (``gen_ai.client.operation.duration``, ``gen_ai.client.token.usage``) and
are latenzy-namespaced where the conventions have no client-side metric yet
(TTFT, throughput). Attributes use ``gen_ai.system`` / ``gen_ai.request.model``
plus latenzy dimensions (``latenzy.endpoint`` / ``latenzy.prompt_class`` /
``latenzy.source``), so the series line up with an OTel GenAI pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from latenzy.probe import Outcome, ProbeResult

if TYPE_CHECKING:
    from opentelemetry.metrics import Meter
    from opentelemetry.sdk.metrics import MeterProvider

_INSTALL_HINT = "the OpenTelemetry bridge requires the 'otel' extra: pip install 'latenzy[otel]'"


def _require_metrics_api() -> Any:
    try:
        from opentelemetry import metrics
    except ModuleNotFoundError as exc:  # pragma: no cover - trivial guard
        raise ImportError(_INSTALL_HINT) from exc
    return metrics


class OTelBridge:
    """A `RecordSink` that records into OpenTelemetry instruments.

    Pass an OTel ``Meter`` (from your app's configured provider) or leave it None
    to use the global meter provider.
    """

    def __init__(self, meter: Meter | None = None) -> None:
        metrics = _require_metrics_api()
        m = meter if meter is not None else metrics.get_meter("latenzy")
        self._duration = m.create_histogram(
            "gen_ai.client.operation.duration",
            unit="s",
            description="Total LLM request duration.",
        )
        self._ttft = m.create_histogram(
            "latenzy.ttft.duration",
            unit="s",
            description="Time to first streamed token.",
        )
        self._tokens = m.create_histogram(
            "gen_ai.client.token.usage",
            unit="{token}",
            description="Number of output tokens per request.",
        )
        self._throughput = m.create_histogram(
            "latenzy.output.throughput",
            unit="{token}/s",
            description="Streaming output throughput over the generation span.",
        )
        self._probes = m.create_counter(
            "latenzy.probes",
            unit="{probe}",
            description="Probe attempts by outcome.",
        )

    def record(self, result: ProbeResult, source: str = "synthetic") -> None:
        attrs = {
            "gen_ai.system": result.provider,
            "gen_ai.request.model": result.model,
            "latenzy.endpoint": result.endpoint,
            "latenzy.prompt_class": result.prompt_class,
            "latenzy.source": source,
        }
        self._probes.add(1, {**attrs, "latenzy.outcome": result.outcome.value})
        if result.outcome is not Outcome.ok:
            return
        if result.ttft_seconds is not None:
            self._ttft.record(result.ttft_seconds, attrs)
        if result.duration_seconds is not None:
            self._duration.record(result.duration_seconds, attrs)
        if result.output_tokens is not None:
            self._tokens.record(result.output_tokens, {**attrs, "gen_ai.token.type": "output"})
        tps = result.tokens_per_second
        if tps is not None:
            self._throughput.record(tps, attrs)


def build_meter_provider(endpoint: str | None = None) -> MeterProvider:
    """Build an SDK `MeterProvider` for the `latenzy run` standalone path.

    With ``endpoint`` set, exports over OTLP/HTTP; otherwise prints to the console
    (handy for local verification). Apps that already run OpenTelemetry should
    instead pass their own ``Meter`` to `OTelBridge` and skip this.
    """
    _require_metrics_api()
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import (
        ConsoleMetricExporter,
        PeriodicExportingMetricReader,
    )

    exporter: Any
    if endpoint:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

        exporter = OTLPMetricExporter(endpoint=endpoint)
    else:
        exporter = ConsoleMetricExporter()
    reader = PeriodicExportingMetricReader(exporter)
    return MeterProvider(metric_readers=[reader])
