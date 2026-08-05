# Security

## Reporting a vulnerability

Email **amit.patole@gmail.com** with details and a reproduction. Please do not
open a public issue for undisclosed vulnerabilities.

## Security posture

latenzy holds provider API keys and runs a network listener, so it is built to
fail closed:

- **Secrets from the environment only.** API keys are read from env vars
  (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, or a configured
  `api_key_env`). A literal key in a config file is rejected by schema. Keys are
  sent only in request headers and never appear in logs, URLs, metrics, or error
  output. `latenzy doctor` reports key presence, never key values.
- **Exporter binds loopback by default.** Binding a routable interface without an
  auth token refuses to start. The bearer token is compared in constant time
  (`hmac.compare_digest`).
- **Bounded resources.** Each probe has a hard overall deadline; SSE streams are
  read with per-line (512 KB) and per-stream (8 MB) caps and a JSON nesting-depth
  limit; the metrics server caps concurrent connections and serves one request
  per connection (no keep-alive slot holding).
- **Hostile-response tolerant.** Every byte from a provider endpoint is treated as
  untrusted: non-dict and wrong-shaped payloads are rejected, reported token
  counts are sanity-bounded, and any parse failure fails closed to an `error`
  outcome without crashing the probe or the monitor loop.
- **Deploy bundle.** No default secrets (Grafana admin password is mandatory; the
  exporter token comes from a mounted secret file). Container images are pinned by
  digest; the image runs as a non-root user; a `.dockerignore` keeps secrets and
  local files out of the build context. Prometheus and Grafana UIs publish to
  loopback only.

## Operator guidance (by design)

latenzy is an **outbound prober you aim at endpoints you choose**. Two behaviors
follow directly from that and are the operator's responsibility, not defects:

- **`base_url` connects wherever you point it.** Do not configure a `base_url`
  (or an endpoint) that targets internal services or a cloud metadata address
  (e.g. `169.254.169.254`); the prober will faithfully POST to whatever you set.
- **`api_key_env` reads whatever env var you name** and sends its value as the
  provider auth header. Point it at your key, not at other secrets.
- **Treat `/metrics` as trusted-network.** Keep it on loopback (default) or behind
  the auth token on a trusted network; it is a monitoring endpoint, not a
  hardened public service.
- **`otel.endpoint` connects wherever you point it** (like `base_url`): the
  OpenTelemetry bridge exports to the OTLP collector you configure. It is
  validated to be an `http(s)` URL; aim it at your own collector.

## Verification

Every security control above is pinned by a regression test in
`tests/test_security.py`. The suite was developed through an audit → fix →
multi-round adversarial red-team loop.
