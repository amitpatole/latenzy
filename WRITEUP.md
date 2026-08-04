# latenzy — per-model LLM latency monitoring

## What it is

latenzy is a synthetic prober and Prometheus exporter, with prebuilt Grafana
dashboards, that measures per-model large-language-model latency for Claude,
OpenAI, and Gemini — at model-ID granularity (`claude-sonnet-4-6` vs `gpt-4o`
vs `gemini-2.0-flash`), not at the lab/provider level.

## Why it exists

Provider status pages report whether a lab is up; public benchmarks report
latency measured from someone else's infrastructure on someone else's account.
Neither answers the question an enterprise actually has: *what latency does **my**
account get from **each model**, right now?* LLM latency is tenant-specific — it
depends on your rate-limit tier, your region, and the path you take to the model
(direct API vs Bedrock vs Vertex). Two customers calling the same model ID see
different p95s. Only a prober running inside your own network, on your own keys,
can measure it. latenzy is that prober.

## How it works

- **Prober.** On a fixed interval, latenzy sends small synthetic requests
  (default: every 5 minutes, ≤16 output tokens, so cost is negligible) to each
  configured `(provider, model, endpoint, prompt_class)` and measures the
  streaming response: time to first token (TTFT), total duration, and output
  tokens per second.
- **Exporter.** Measurements are exposed as Prometheus histograms
  (`latenzy_ttft_seconds`, `latenzy_request_duration_seconds`,
  `latenzy_output_tokens_per_second`) plus an outcome counter
  (`ok`/`rate_limited`/`timeout`/`error`) and a last-success gauge. Prometheus
  recording rules pre-compute hourly and daily p50/p95/p99 series; alert rules
  cover staleness, TTFT SLO breach, rate-limit pressure, and failure ratio.
- **Dashboards.** A Grafana model-comparison dashboard (Grafana dashboard
  library ID 25642) is the headline view: pick N models and compare TTFT p95,
  total-latency p95, throughput, and 429 rate side by side, filterable by
  provider, model, endpoint, and prompt class.
- **Standalone bundle.** For sites without an existing stack, a docker-compose
  bundle runs the prober, Prometheus, and Grafana with the dashboard
  pre-provisioned — one command.

## Architecture

`config` (pydantic v2, YAML; keys from env only) → `prober` (async fan-out with
bounded concurrency) → per-provider `ProviderProbe` (SSE streaming over httpx,
measuring TTFT) → `metrics` (Prometheus histograms; successful probes only, so
errors never skew percentiles) → `exporter` (fail-closed `/metrics` server:
loopback by default, auth required on any routable bind, constant-time token
comparison). Every byte from a provider endpoint is treated as untrusted.

## Security

latenzy holds provider API keys and runs a network listener, so it was hardened
through a four-round audit → red-team loop before its first release: bounded
probe streaming and an overall per-probe deadline, fail-closed response parsing
(no malformed provider byte can crash the monitor), a connection-capped
exporter with no keep-alive slot holding, and a no-default-secret deploy bundle
with digest-pinned images. See `SECURITY.md` for the full posture.

## How to cite

See `CITATION.cff`. This release is archived on Zenodo with a DOI (added to the
README badge and `CITATION.cff` once minted).

## License

AGPL-3.0-only. Dual licensing is available for enterprises — contact the author.

— amitpatole
