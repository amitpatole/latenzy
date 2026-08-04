"""Regression tests pinning the phase-3 security fixes. Each test runs the
exploit shape against the fixed code and asserts it is blocked."""

from __future__ import annotations

import asyncio
import socket
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from prometheus_client import CollectorRegistry

from latenzy.config import ExporterConfig, ProviderConfig, ProviderKind
from latenzy.exporter import MAX_CONCURRENT_CONNECTIONS, MetricsServer
from latenzy.probe import Outcome
from latenzy.providers import PROBE_CLASSES


def make_probe(kind: ProviderKind, transport: httpx.AsyncBaseTransport) -> Any:
    cfg = ProviderConfig(provider=kind, models=["some-model"])
    return PROBE_CLASSES[kind](cfg, httpx.AsyncClient(transport=transport))


class _StreamingTransport(httpx.AsyncBaseTransport):
    def __init__(self, stream: httpx.AsyncByteStream) -> None:
        self._stream = stream

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=self._stream)


class _SlowDrip(httpx.AsyncByteStream):
    """Keeps the connection alive forever with periodic pings — each read is
    fast, so per-chunk read timeouts never fire."""

    async def __aiter__(self) -> AsyncIterator[bytes]:
        while True:
            yield b'data: {"type": "ping"}\n\n'
            await asyncio.sleep(0.02)


class _NewlineFreeFlood(httpx.AsyncByteStream):
    """Streams megabytes without a newline — naive line buffering would grow
    without bound."""

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for _ in range(200):
            yield b"x" * 65536


async def test_slow_drip_stream_hits_overall_deadline(api_keys: None) -> None:
    probe = make_probe(ProviderKind.anthropic, _StreamingTransport(_SlowDrip()))
    started = time.perf_counter()
    result = await probe.probe("some-model", "small", "p", 16, 0.5)
    elapsed = time.perf_counter() - started
    assert result.outcome is Outcome.timeout
    assert elapsed < 5, f"probe was not bounded by the deadline (took {elapsed:.1f}s)"


async def test_newline_free_flood_is_bounded(api_keys: None) -> None:
    probe = make_probe(ProviderKind.openai, _StreamingTransport(_NewlineFreeFlood()))
    result = await probe.probe("some-model", "small", "p", 16, 30.0)
    assert result.outcome is Outcome.error


def _body_transport(body: bytes) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    return httpx.MockTransport(handler)


# Round 2: hostile provider bytes must never crash a probe (and thus the monitor).
HOSTILE_PAYLOADS = [
    b"data: 5\n\n",  # non-dict top-level -> would hit .get() on an int
    b"data: null\n\n",
    b"data: []\n\n",
    b'data: "gotcha"\n\n',
    b'data: {"choices": [42]}\n\n',  # type-confusion: list item not a dict
    b'data: {"choices": [{"delta": 7}]}\n\n',  # delta not a dict
    b'data: {"candidates": [1]}\n\n',
    b'data: {"usage": 5}\n\n',  # usage not a dict
    b'data: {"usageMetadata": {"candidatesTokenCount": true}}\n\n',  # bool token
    b"data: " + b"[" * 6000 + b"]" * 6000 + b"\n\n",  # deep nesting -> RecursionError
]


@pytest.mark.parametrize("kind", list(ProviderKind))
@pytest.mark.parametrize("payload", HOSTILE_PAYLOADS)
async def test_hostile_payload_never_crashes_probe(
    kind: ProviderKind, payload: bytes, api_keys: None
) -> None:
    probe = make_probe(kind, _body_transport(payload))
    # Must return an Outcome, never raise.
    result = await probe.probe("some-model", "small", "p", 16, 5.0)
    assert result.outcome in set(Outcome)


# Per provider: a token-bearing delta line, then a usage line whose count is %d.
_ABSURD_TOKEN_STREAMS = {
    ProviderKind.anthropic: (
        b'data: {"type": "content_block_delta", "delta": {"text": "x"}}',
        b'data: {"type": "message_delta", "usage": {"output_tokens": %d}}',
    ),
    ProviderKind.openai: (
        b'data: {"choices": [{"delta": {"content": "x"}}]}',
        b'data: {"usage": {"completion_tokens": %d}}',
    ),
    ProviderKind.gemini: (
        b'data: {"candidates": [{"content": {"parts": [{"text": "x"}]}}]}',
        b'data: {"usageMetadata": {"candidatesTokenCount": %d}}',
    ),
}


async def test_bracket_heavy_token_text_is_not_falsely_dropped(api_keys: None) -> None:
    # Round 3: an honest delta whose TEXT contains many brackets must not trip
    # the depth limiter (brackets inside string literals are not structure).
    text = "[" * 100 + "{" * 100
    delta = f'data: {{"type": "content_block_delta", "delta": {{"text": "{text}"}}}}'.encode()
    usage = b'data: {"type": "message_delta", "usage": {"output_tokens": 5}}'
    body = delta + b"\n\n" + usage + b"\n\n"
    probe = make_probe(ProviderKind.anthropic, _body_transport(body))
    result = await probe.probe("some-model", "small", "p", 16, 5.0)
    assert result.outcome is Outcome.ok  # token was seen, not dropped
    assert result.output_tokens == 5


async def test_closers_hidden_in_strings_cannot_smuggle_deep_nesting(api_keys: None) -> None:
    # Round 3 bypass: hide "]" in a string then nest deeply for real. The
    # string-aware scanner must still count the real depth and reject (or, at
    # worst, the RecursionError safety net degrades it to error — never a crash).
    payload = b'data: {"x":"' + b"]" * 100 + b'","y":' + b"[" * 5000 + b"]" * 5000 + b"}\n\n"
    probe = make_probe(ProviderKind.openai, _body_transport(payload))
    result = await probe.probe("some-model", "small", "p", 16, 5.0)
    assert result.outcome in set(Outcome)  # never raises


@pytest.mark.parametrize("kind", list(ProviderKind))
async def test_absurd_token_count_does_not_crash_or_poison(
    kind: ProviderKind, api_keys: None
) -> None:
    # 10**400 would overflow float in the tokens/sec division; it must be
    # dropped as an implausible count, not observed and not raised.
    token_delta, usage_tmpl = _ABSURD_TOKEN_STREAMS[kind]
    body = token_delta + b"\n\n" + (usage_tmpl % (10**400)) + b"\n\n"
    probe = make_probe(kind, _body_transport(body))
    result = await probe.probe("some-model", "small", "p", 16, 5.0)
    assert result.outcome is Outcome.ok  # a token was seen
    assert result.output_tokens is None  # implausible count rejected
    assert result.tokens_per_second is None


async def test_run_forever_survives_a_failing_cycle(metrics: Any, api_keys: None) -> None:
    from latenzy.prober import Prober
    from tests.conftest import make_config

    prober = Prober(make_config(), metrics, transport=_body_transport(b"data: 5\n\n"))
    stop = asyncio.Event()

    async def stop_after_two() -> None:
        await asyncio.sleep(0.05)
        stop.set()

    # run_forever must not raise even though every probe payload is hostile.
    try:
        await asyncio.wait_for(
            asyncio.gather(prober.run_forever(stop), stop_after_two()), timeout=5
        )
    finally:
        await prober.aclose()


def test_metrics_server_refuses_connections_beyond_cap(registry: CollectorRegistry) -> None:
    server = MetricsServer(ExporterConfig(host="127.0.0.1", port=0), registry)
    server.start()  # close() blocks unless serve_forever is running
    try:
        fakes = [socket.socket() for _ in range(MAX_CONCURRENT_CONNECTIONS)]
        try:
            for sock in fakes:
                assert server._server.verify_request(sock, ("127.0.0.1", 1))
            overflow = socket.socket()
            try:
                assert not server._server.verify_request(overflow, ("127.0.0.1", 1))
                # Draining one connection frees a slot.
                server._server.shutdown_request(fakes[0])
                assert server._server.verify_request(overflow, ("127.0.0.1", 1))
            finally:
                overflow.close()
        finally:
            for sock in fakes:
                sock.close()
    finally:
        server.close()


@pytest.mark.parametrize(
    "model",
    ["../../../etc/passwd", "m?key=steal", "m/../../v1/other", "m odel", "", "m\n"],
)
def test_hostile_model_ids_rejected(model: str) -> None:
    with pytest.raises(ValueError):
        ProviderConfig(provider=ProviderKind.gemini, models=[model])


@pytest.mark.parametrize(
    "model", ["claude-sonnet-4-6", "gpt-4o", "gemini-2.0-flash", "claude-haiku-4-5-20251001"]
)
def test_real_model_ids_accepted(model: str) -> None:
    ProviderConfig(provider=ProviderKind.anthropic, models=[model])


@pytest.mark.parametrize("endpoint", ["bad endpoint", 'x"} evil', "a" * 65, ""])
def test_hostile_endpoint_labels_rejected(endpoint: str) -> None:
    with pytest.raises(ValueError):
        ProviderConfig(provider=ProviderKind.openai, models=["m"], endpoint=endpoint)


@pytest.mark.parametrize(
    "url",
    ["ftp://host", "file:///etc/passwd", "https://", "https://h?x=1", "https://h#frag", "host"],
)
def test_hostile_base_urls_rejected(url: str) -> None:
    with pytest.raises(ValueError):
        ProviderConfig(provider=ProviderKind.openai, models=["m"], base_url=url)


@pytest.mark.parametrize("env", ["BAD-NAME", "has space", "x\x1b[31m", "1STARTSDIGIT", "a\nb"])
def test_hostile_env_var_names_rejected(env: str) -> None:
    with pytest.raises(ValueError):
        ProviderConfig(provider=ProviderKind.openai, models=["m"], api_key_env=env)
    with pytest.raises(ValueError):
        ExporterConfig(auth_token_env=env)


@pytest.mark.parametrize("host", ["has space", "h\x1b[2Jx", "a\nb", "x" * 300])
def test_hostile_host_values_rejected(host: str) -> None:
    with pytest.raises(ValueError):
        ExporterConfig(host=host)


def test_real_env_names_and_hosts_accepted() -> None:
    ProviderConfig(provider=ProviderKind.openai, models=["m"], api_key_env="MY_KEY_1")
    ExporterConfig(host="0.0.0.0", auth_token_env="LATENZY_TOKEN")
    ExporterConfig(host="metrics.internal.corp")


def test_base_url_trailing_slash_normalized() -> None:
    cfg = ProviderConfig(provider=ProviderKind.openai, models=["m"], base_url="https://gw.corp/")
    assert cfg.resolved_base_url == "https://gw.corp"
