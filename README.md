# latenzy

Per-model LLM latency monitoring for enterprises. latenzy is a synthetic prober and
Prometheus exporter that measures what the lab-level status pages can't: the latency
**your** account gets from **each model** — `claude-sonnet-4-6` vs `gpt-4o` vs
`gemini-2.0-flash`, not "Anthropic is up".

Latency is tenant-specific: it depends on your rate-limit tier, your region, and the
path you take to the model (direct API, Bedrock, Vertex). latenzy runs inside your
network on your keys and exports per-model metrics your existing Prometheus + Grafana
stack can alert on.

## What it measures

Every probe cycle, for each configured `(provider, model, endpoint, prompt_class)`:

| Metric | Meaning |
|---|---|
| `latenzy_ttft_seconds` | time to first streamed token (histogram) |
| `latenzy_request_duration_seconds` | total request duration (histogram) |
| `latenzy_output_tokens_per_second` | streaming throughput over the generation span (histogram) |
| `latenzy_probes_total{outcome=...}` | probe count by `ok` / `rate_limited` / `timeout` / `error` |
| `latenzy_last_success_timestamp_seconds` | staleness signal for alerting |

Histograms are observed only for successful probes, so failures never skew latency
percentiles. Prompts are deterministic per `prompt_class` (small/medium/large) —
comparing models on unequal inputs is meaningless.

## Quick start

```bash
pip install latenzy

export ANTHROPIC_API_KEY=... OPENAI_API_KEY=... GEMINI_API_KEY=...
latenzy doctor -c latenzy.yaml   # validate config, check keys are present
latenzy once   -c latenzy.yaml   # one probe cycle, human-readable results
latenzy run    -c latenzy.yaml   # probe on an interval + serve /metrics
```

See [`latenzy.example.yaml`](latenzy.example.yaml) for the full configuration.
API keys are read from environment variables only — they have no place in config files.

## Security posture

- Binds `127.0.0.1` by default. Binding a routable interface **refuses to start**
  unless `exporter.auth_token_env` is set; the token is checked in constant time.
- API keys are sent in request headers only and never appear in logs, URLs, metrics,
  or error output.
- Probe cost is bounded: `max_output_tokens` defaults to 16.

## Status

Phase 1 (prober + exporter, Anthropic / OpenAI / Gemini). Coming next: prebuilt
Grafana dashboards + recording/alert rules, a docker-compose standalone bundle, and
passive OpenTelemetry middleware for real-traffic latency.

License: AGPL-3.0-only. Dual licensing available for enterprises — contact the author.

— amitpatole
