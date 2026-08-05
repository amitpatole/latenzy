"""The recording interface shared by every metrics backend.

`Metrics` (Prometheus) and `OTelBridge` both satisfy `RecordSink`, so the prober
and the live recorder can fan out to either or both through one call.
"""

from __future__ import annotations

import contextlib
from typing import Protocol, runtime_checkable

from latenzy.probe import ProbeResult


@runtime_checkable
class RecordSink(Protocol):
    def record(self, result: ProbeResult, source: str = ...) -> None: ...


class FanoutSink:
    """Fan one recording out to several sinks (e.g. Prometheus + OpenTelemetry).

    A sink that raises must not stop the others — a broken exporter should never
    take down the monitor loop — so exceptions are swallowed per sink.
    """

    def __init__(self, *sinks: RecordSink) -> None:
        self._sinks = sinks

    def record(self, result: ProbeResult, source: str = "synthetic") -> None:
        for sink in self._sinks:
            # One bad sink (e.g. a down exporter) must not blind the others.
            with contextlib.suppress(Exception):
                sink.record(result, source)
