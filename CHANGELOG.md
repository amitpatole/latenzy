# Changelog

## Unreleased

- Passive live-traffic instrumentation: `LiveRecorder` / `LiveObservation` /
  `classify_prompt` / `measure_stream` record real application LLM-call latency
  into the same metric names under a new `source="live"` label (prober traffic
  is `source="synthetic"`). Label values are charset-validated and token counts
  bounded, matching the prober's hardening. Recording rules, the Grafana
  dashboard (new `source` filter), and `examples/demo_live.py` updated in
  lockstep. Metric semantics follow the OpenTelemetry GenAI conventions.

## 0.1.0 — 2026-08-04

First real release.

- Synthetic prober + Prometheus exporter for Anthropic, OpenAI, and Gemini.
  Per-model TTFT, total duration, streaming tokens/sec, and outcome metrics;
  fail-closed `/metrics` server; `latenzy run` / `once` / `doctor` CLI.
- Grafana model-comparison dashboard (`dashboards/`, library ID 25642),
  hourly/daily recording rules and alert rules (`prometheus/`), and a
  docker-compose standalone bundle (`deploy/`) with prober + Prometheus +
  Grafana pre-provisioned.
- Security-hardened through a four-round audit → red-team loop: bounded probe
  streaming, fail-closed response parsing, connection-capped exporter,
  no-default-secret deploy bundle with digest-pinned images. See `SECURITY.md`.

## 0.0.1 — 2026-08-04

- Name reservation placeholder on PyPI/TestPyPI; AGPL-3.0-only; `CITATION.cff`.
