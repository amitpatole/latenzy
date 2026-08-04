from __future__ import annotations

import httpx
import pytest
from prometheus_client import CollectorRegistry

from latenzy.config import Config
from latenzy.metrics import Metrics


@pytest.fixture()
def registry() -> CollectorRegistry:
    return CollectorRegistry()


@pytest.fixture()
def metrics(registry: CollectorRegistry) -> Metrics:
    return Metrics(registry)


@pytest.fixture()
def api_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")


def sse(*payloads: str) -> str:
    return "".join(f"data: {p}\n\n" for p in payloads)


ANTHROPIC_STREAM = sse(
    '{"type": "message_start", "message": {}}',
    '{"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Because"}}',
    '{"type": "content_block_delta", "delta": {"type": "text_delta", "text": " Rayleigh"}}',
    '{"type": "message_delta", "usage": {"output_tokens": 12}}',
    '{"type": "message_stop"}',
)

OPENAI_STREAM = sse(
    '{"choices": [{"delta": {"role": "assistant"}}]}',
    '{"choices": [{"delta": {"content": "Because"}}]}',
    '{"choices": [{"delta": {"content": " scattering"}}]}',
    '{"choices": [], "usage": {"completion_tokens": 9, "prompt_tokens": 14}}',
    "[DONE]",
)

GEMINI_STREAM = sse(
    '{"candidates": [{"content": {"parts": [{"text": "Because of Rayleigh"}]}}]}',
    '{"candidates": [{"content": {"parts": [{"text": " scattering."}]}}],'
    ' "usageMetadata": {"candidatesTokenCount": 7}}',
)


def stream_transport(body: str, status_code: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            content=body.encode(),
            headers={"content-type": "text/event-stream"},
        )

    return httpx.MockTransport(handler)


def make_config(**overrides: object) -> Config:
    data: dict[str, object] = {
        "providers": [
            {"provider": "anthropic", "models": ["claude-sonnet-4-6"]},
            {"provider": "openai", "models": ["gpt-4o"]},
            {"provider": "gemini", "models": ["gemini-2.0-flash"]},
        ],
        "probe": {"interval_seconds": 10, "timeout_seconds": 5},
    }
    data.update(overrides)
    return Config.model_validate(data)
