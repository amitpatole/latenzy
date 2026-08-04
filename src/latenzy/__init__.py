"""latenzy — per-model LLM latency monitoring.

A synthetic prober and Prometheus exporter that measures per-model latency
(TTFT, total duration, streaming throughput, rate-limit pressure) across
Claude, OpenAI, and Gemini models.
"""

from latenzy.config import Config, ExporterConfig, ProbeConfig, ProviderConfig, load_config
from latenzy.probe import Outcome, ProbeResult

__version__ = "0.0.1"

__all__ = [
    "Config",
    "ExporterConfig",
    "Outcome",
    "ProbeConfig",
    "ProbeResult",
    "ProviderConfig",
    "__version__",
    "load_config",
]
