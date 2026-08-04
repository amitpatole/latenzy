# latenzy

**Per-model LLM latency monitoring for enterprises.**

latenzy is a synthetic prober and Prometheus exporter, with prebuilt Grafana
dashboards, that measures what lab-level status pages can't: the latency **your**
account gets from **each model** — `claude-sonnet-4-6` vs `gpt-4o` vs
`gemini-2.0-flash`, not "Anthropic is up".

Latency is tenant-specific: it depends on your rate-limit tier, your region, and
the path you take to the model (direct API, Bedrock, Vertex). latenzy runs inside
your network on your keys and exports per-model metrics your existing Prometheus +
Grafana stack can alert on.

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21796983.svg)](https://doi.org/10.5281/zenodo.21796983)
[![PyPI](https://img.shields.io/pypi/v/latenzy.svg)](https://pypi.org/project/latenzy/)

## What it measures

Every probe cycle, for each `(source, provider, model, endpoint, prompt_class)`:

| Metric | Meaning |
|---|---|
| `latenzy_ttft_seconds` | time to first streamed token (histogram) |
| `latenzy_request_duration_seconds` | total request duration (histogram) |
| `latenzy_output_tokens_per_second` | streaming throughput (histogram) |
| `latenzy_probes_total{outcome=...}` | count by `ok` / `rate_limited` / `timeout` / `error` |
| `latenzy_last_success_timestamp_seconds` | staleness signal for alerting |

The `source` label is `synthetic` for the prober's canaries and `live` for real
application traffic ([Live traffic](live-traffic.md)) — one dashboard shows both.

## Where to go next

- [Getting started](getting-started.md) — install, configure, first probe cycle.
- [Configuration](configuration.md) — the full YAML reference.
- [Dashboards & alerts](dashboards.md) — the Grafana dashboard (library ID 25642)
  and Prometheus rules.
- [Standalone bundle](standalone.md) — `docker compose up` with no existing stack.
- [Live traffic](live-traffic.md) — instrument your real LLM calls.
- [Security](security.md) — posture and operator guidance.

License: AGPL-3.0-only. Dual licensing available for enterprises.

*— amitpatole*
