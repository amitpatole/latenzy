from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from prometheus_client import CollectorRegistry

from latenzy.config import ConfigError, ExporterConfig
from latenzy.exporter import MetricsServer, resolve_auth_token
from latenzy.metrics import Metrics
from latenzy.probe import Outcome, ProbeResult


@pytest.fixture()
def server(registry: CollectorRegistry, metrics: Metrics) -> Iterator[MetricsServer]:
    metrics.record(
        ProbeResult(
            provider="openai",
            model="gpt-4o",
            endpoint="direct",
            prompt_class="small",
            outcome=Outcome.ok,
            ttft_seconds=0.3,
            duration_seconds=1.0,
            output_tokens=8,
        )
    )
    srv = MetricsServer(ExporterConfig(host="127.0.0.1", port=0), registry)
    srv.start()
    yield srv
    srv.close()


def test_serves_metrics_on_loopback_without_auth(server: MetricsServer) -> None:
    body = httpx.get(f"http://127.0.0.1:{server.port}/metrics").raise_for_status().text
    assert 'latenzy_ttft_seconds_count{endpoint="direct"' in body
    assert "latenzy_probes_total" in body


def test_unknown_path_404(server: MetricsServer) -> None:
    assert httpx.get(f"http://127.0.0.1:{server.port}/nope").status_code == 404


def test_non_loopback_without_token_refuses_to_start(registry: CollectorRegistry) -> None:
    with pytest.raises(ConfigError, match="refusing to bind non-loopback"):
        MetricsServer(ExporterConfig(host="0.0.0.0", port=0), registry)


def test_unknown_hostname_treated_as_routable() -> None:
    with pytest.raises(ConfigError):
        resolve_auth_token(ExporterConfig(host="metrics.internal", port=0))


def test_token_env_set_but_missing_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LATENZY_TOKEN", raising=False)
    with pytest.raises(ConfigError, match="LATENZY_TOKEN"):
        resolve_auth_token(ExporterConfig(host="127.0.0.1", port=0, auth_token_env="LATENZY_TOKEN"))


def test_auth_required_when_token_configured(
    registry: CollectorRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LATENZY_TOKEN", "sekrit")
    srv = MetricsServer(
        ExporterConfig(host="127.0.0.1", port=0, auth_token_env="LATENZY_TOKEN"), registry
    )
    srv.start()
    try:
        base = f"http://127.0.0.1:{srv.port}/metrics"
        assert httpx.get(base).status_code == 401
        assert httpx.get(base, headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert httpx.get(base, headers={"Authorization": "Bearer sekrit"}).status_code == 200
    finally:
        srv.close()
