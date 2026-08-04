from __future__ import annotations

import httpx
import pytest

from latenzy.config import ProviderConfig, ProviderKind
from latenzy.probe import Outcome
from latenzy.providers import PROBE_CLASSES
from latenzy.providers.base import ProviderProbe
from tests.conftest import ANTHROPIC_STREAM, GEMINI_STREAM, OPENAI_STREAM, stream_transport

STREAMS = {
    ProviderKind.anthropic: (ANTHROPIC_STREAM, 12),
    ProviderKind.openai: (OPENAI_STREAM, 9),
    ProviderKind.gemini: (GEMINI_STREAM, 7),
}


def make_probe(kind: ProviderKind, transport: httpx.MockTransport) -> ProviderProbe:
    cfg = ProviderConfig(provider=kind, models=["some-model"])
    return PROBE_CLASSES[kind](cfg, httpx.AsyncClient(transport=transport))


@pytest.mark.parametrize("kind", list(ProviderKind))
async def test_successful_probe_measures_ttft_and_tokens(
    kind: ProviderKind, api_keys: None
) -> None:
    body, expected_tokens = STREAMS[kind]
    probe = make_probe(kind, stream_transport(body))
    result = await probe.probe("some-model", "small", "why is the sky blue?", 16, 5.0)
    assert result.outcome is Outcome.ok
    assert result.ttft_seconds is not None and result.ttft_seconds >= 0
    assert result.duration_seconds is not None
    assert result.duration_seconds >= result.ttft_seconds
    assert result.output_tokens == expected_tokens
    assert result.provider == kind.value
    assert result.endpoint == "direct"


@pytest.mark.parametrize("kind", list(ProviderKind))
async def test_429_maps_to_rate_limited(kind: ProviderKind, api_keys: None) -> None:
    probe = make_probe(kind, stream_transport("", status_code=429))
    result = await probe.probe("some-model", "small", "p", 16, 5.0)
    assert result.outcome is Outcome.rate_limited


@pytest.mark.parametrize("status", [400, 401, 500, 529])
async def test_http_errors_map_to_error(status: int, api_keys: None) -> None:
    probe = make_probe(ProviderKind.anthropic, stream_transport("", status_code=status))
    result = await probe.probe("some-model", "small", "p", 16, 5.0)
    assert result.outcome is Outcome.error


async def test_timeout_maps_to_timeout(api_keys: None) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("probe timed out")

    probe = make_probe(ProviderKind.openai, httpx.MockTransport(handler))
    result = await probe.probe("some-model", "small", "p", 16, 5.0)
    assert result.outcome is Outcome.timeout


async def test_empty_stream_is_error_not_ok(api_keys: None) -> None:
    probe = make_probe(ProviderKind.anthropic, stream_transport('data: {"type": "ping"}\n\n'))
    result = await probe.probe("some-model", "small", "p", 16, 5.0)
    assert result.outcome is Outcome.error


@pytest.mark.parametrize("kind", list(ProviderKind))
async def test_api_key_sent_in_header_not_url(kind: ProviderKind, api_keys: None) -> None:
    seen: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        body, _ = STREAMS[kind]
        return httpx.Response(200, content=body.encode())

    probe = make_probe(kind, httpx.MockTransport(handler))
    await probe.probe("some-model", "small", "p", 16, 5.0)
    request = seen["request"]
    assert "key" not in str(request.url).lower() or "test-" not in str(request.url)
    header_values = " ".join(request.headers.values())
    assert f"test-{kind.value}-key" in header_values
