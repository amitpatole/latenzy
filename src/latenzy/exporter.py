"""The /metrics HTTP server.

Security posture (fail closed):
- binding a non-loopback interface without an auth token refuses to start;
- token comparison is constant-time;
- GET only, no request bodies read, per-connection timeout, no server banner.
"""

from __future__ import annotations

import hmac
import ipaddress
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from prometheus_client.exposition import CONTENT_TYPE_LATEST, generate_latest
from prometheus_client.registry import CollectorRegistry

from latenzy.config import ConfigError, ExporterConfig


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        # Unknown hostname: treat as routable so auth is required (fail closed).
        return False


def resolve_auth_token(config: ExporterConfig) -> str | None:
    token: str | None = None
    if config.auth_token_env:
        token = os.environ.get(config.auth_token_env) or None
        if token is None:
            raise ConfigError(
                f"exporter.auth_token_env is set but {config.auth_token_env} is empty or unset"
            )
    if token is None and not _is_loopback(config.host):
        raise ConfigError(
            f"refusing to bind non-loopback host {config.host!r} without an auth token; "
            "set exporter.auth_token_env"
        )
    return token


class MetricsServer:
    def __init__(self, config: ExporterConfig, registry: CollectorRegistry) -> None:
        token = resolve_auth_token(config)
        registry_ref = registry

        class Handler(BaseHTTPRequestHandler):
            server_version = "latenzy"
            sys_version = ""
            timeout = 10
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:
                if token is not None and not self._authorized():
                    self._respond(401, b"unauthorized\n", "text/plain")
                    return
                if self.path.split("?", 1)[0] not in ("/", "/metrics"):
                    self._respond(404, b"not found\n", "text/plain")
                    return
                self._respond(200, generate_latest(registry_ref), CONTENT_TYPE_LATEST)

            def _authorized(self) -> bool:
                header = self.headers.get("Authorization", "")
                expected = f"Bearer {token}"
                return hmac.compare_digest(header.encode(), expected.encode())

            def _respond(self, status: int, body: bytes, content_type: str) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                pass  # request paths/headers stay out of logs

        self._server = ThreadingHTTPServer((config.host, config.port), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
