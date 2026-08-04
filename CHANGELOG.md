# Changelog

## Unreleased

- Phase 1: synthetic prober + Prometheus exporter for Anthropic, OpenAI, and
  Gemini. Per-model TTFT, total duration, streaming tokens/sec, and outcome
  metrics; fail-closed `/metrics` server; `latenzy run` / `once` / `doctor` CLI.
- Phase 2: Grafana model-comparison dashboard (`dashboards/`), hourly/daily
  recording rules and alert rules (`prometheus/`), and a docker-compose
  standalone bundle (`deploy/`) with prober + Prometheus + Grafana
  pre-provisioned.

## 0.0.1 — 2026-08-04

- Name reservation placeholder on PyPI/TestPyPI; AGPL-3.0-only; `CITATION.cff`.
