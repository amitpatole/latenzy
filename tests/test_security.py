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


def test_base_url_trailing_slash_normalized() -> None:
    cfg = ProviderConfig(provider=ProviderKind.openai, models=["m"], base_url="https://gw.corp/")
    assert cfg.resolved_base_url == "https://gw.corp"
