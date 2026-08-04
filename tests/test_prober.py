from __future__ import annotations

import httpx
from prometheus_client import CollectorRegistry

from latenzy.metrics import Metrics
from latenzy.prober import Prober
from tests.conftest import (
    ANTHROPIC_STREAM,
    GEMINI_STREAM,
    OPENAI_STREAM,
    make_config,
)

BODIES = {
    "api.anthropic.com": ANTHROPIC_STREAM,
    "api.openai.com": OPENAI_STREAM,
    "generativelanguage.googleapis.com": GEMINI_STREAM,
}


def routing_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=BODIES[request.url.host].encode())

    return httpx.MockTransport(handler)


async def test_run_once_probes_every_model_and_records(
    registry: CollectorRegistry, metrics: Metrics, api_keys: None
) -> None:
    prober = Prober(make_config(), metrics, transport=routing_transport())
    try:
        results = await prober.run_once()
    finally:
        await prober.aclose()
    assert len(results) == 3  # one model per provider, one prompt class
    assert all(r.outcome.value == "ok" for r in results)
    for provider, model in [
        ("anthropic", "claude-sonnet-4-6"),
        ("openai", "gpt-4o"),
        ("gemini", "gemini-2.0-flash"),
    ]:
        assert (
            registry.get_sample_value(
                "latenzy_probes_total",
                {
                    "provider": provider,
                    "model": model,
                    "endpoint": "direct",
                    "prompt_class": "small",
                    "outcome": "ok",
                },
            )
            == 1
        )


async def test_prompt_classes_multiply_probe_count(metrics: Metrics, api_keys: None) -> None:
    config = make_config(
        probe={"interval_seconds": 10, "prompt_classes": ["small", "medium", "large"]}
    )
    prober = Prober(config, metrics, transport=routing_transport())
    try:
        results = await prober.run_once()
    finally:
        await prober.aclose()
    assert len(results) == 9
    assert {r.prompt_class for r in results} == {"small", "medium", "large"}
