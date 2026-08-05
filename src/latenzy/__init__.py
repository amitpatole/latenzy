"""latenzy — per-model LLM latency monitoring.

A synthetic prober and Prometheus exporter that measures per-model latency
(TTFT, total duration, streaming throughput, rate-limit pressure) across
Claude, OpenAI, and Gemini models.
"""

from latenzy.config import Config, ExporterConfig, ProbeConfig, ProviderConfig, load_config
from latenzy.live import LiveObservation, LiveRecorder, classify_prompt, measure_stream
from latenzy.metrics import Metrics
from latenzy.probe import Outcome, ProbeResult
from latenzy.sink import FanoutSink, RecordSink

__version__ = "0.1.0"

__all__ = [
    "Config",
    "ExporterConfig",
    "FanoutSink",
    "LiveObservation",
    "LiveRecorder",
    "Metrics",
    "Outcome",
    "ProbeConfig",
    "ProbeResult",
    "ProviderConfig",
    "RecordSink",
    "__version__",
    "classify_prompt",
    "load_config",
    "measure_stream",
]
