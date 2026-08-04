# latenzy · LLM model latency comparison

Per-model LLM latency for **Claude, OpenAI, and Gemini** — at model-ID granularity
(`claude-sonnet-4-6` vs `gpt-4o` vs `gemini-2.0-flash`), not lab-level rollups.

Provider status pages tell you whether a lab is up. This dashboard tells you what
latency **your account** actually gets from **each model**, measured from inside your
own network — because LLM latency depends on your rate-limit tier, your region, and
the path you take to the model (direct API, Bedrock, Vertex).

## What it shows

- **Time to first token (TTFT) p95** per model — hourly window, the number your users feel
- **Total request latency p95** per model
- **Streaming throughput** (output tokens/sec, p50) per model
- **Failure and rate-limit (429) ratio** per model — spot quota pressure before users do
- **Model ranking table** — TTFT p95 over the last hour, worst first
- **Probe staleness** — seconds since each model's last successful probe, for alerting

Everything is filterable by `provider`, `model`, `endpoint` (compare the *same* model
via direct API vs Bedrock vs Vertex), and `prompt_class` (small/medium/large inputs,
since latency scales with prompt size).

## How the data is collected

Metrics come from **[latenzy](https://github.com/amitpatole/latenzy)**, an AGPL
Prometheus exporter that sends small synthetic probe requests to each configured
model on an interval (default: every 5 minutes, max 16 output tokens per probe, so
cost is negligible) and measures the streaming response.

### 1. Install and configure the exporter

```bash
pip install latenzy
```

```yaml
# latenzy.yaml — API keys come from env vars only, never from this file
providers:
  - provider: anthropic        # ANTHROPIC_API_KEY
    models: [claude-sonnet-4-6, claude-haiku-4-5-20251001]
  - provider: openai           # OPENAI_API_KEY
    models: [gpt-4o, gpt-4o-mini]
  - provider: gemini           # GEMINI_API_KEY
    models: [gemini-2.0-flash]
```

```bash
latenzy doctor -c latenzy.yaml   # checks config + keys
latenzy run    -c latenzy.yaml   # serves http://127.0.0.1:9877/metrics
```

### 2. Scrape it and load the recording rules

**Required:** the dashboard panels query pre-computed recording rules
(`latenzy:ttft_seconds:p95_1h`, ...) — without them the panels stay empty. Get
[`recording_rules.yml`](https://github.com/amitpatole/latenzy/blob/main/prometheus/recording_rules.yml)
(and optionally
[`alert_rules.yml`](https://github.com/amitpatole/latenzy/blob/main/prometheus/alert_rules.yml))
from the repo:

```yaml
# prometheus.yml
rule_files:
  - recording_rules.yml
  - alert_rules.yml
scrape_configs:
  - job_name: latenzy
    static_configs:
      - targets: ["localhost:9877"]
```

### 3. Import this dashboard

Import it in Grafana, pick your Prometheus datasource when prompted, and give the
prober one or two probe intervals to produce data.

No existing Prometheus/Grafana? The repo ships a
[docker-compose bundle](https://github.com/amitpatole/latenzy/tree/main/deploy)
that runs prober + Prometheus + Grafana with this dashboard pre-provisioned.
