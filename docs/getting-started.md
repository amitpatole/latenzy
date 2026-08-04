# Getting started

## Install

```bash
pip install latenzy
```

## Configure

Write a `latenzy.yaml`. API keys are read from environment variables only — they
have no place in a config file.

```yaml
providers:
  - provider: anthropic          # key from ANTHROPIC_API_KEY
    endpoint: direct
    models:
      - claude-sonnet-4-6
      - claude-haiku-4-5-20251001
  - provider: openai             # key from OPENAI_API_KEY
    endpoint: direct
    models:
      - gpt-4o
      - gpt-4o-mini
  - provider: gemini             # key from GEMINI_API_KEY
    endpoint: direct
    models:
      - gemini-2.0-flash

probe:
  interval_seconds: 300          # one probe cycle every 5 minutes
  max_output_tokens: 16          # keep probe cost negligible
  prompt_classes: [small]

exporter:
  host: 127.0.0.1                # loopback needs no auth
  port: 9877
```

See [Configuration](configuration.md) for every field.

## Run

```bash
export ANTHROPIC_API_KEY=... OPENAI_API_KEY=... GEMINI_API_KEY=...

latenzy doctor -c latenzy.yaml   # validate config, check keys are present
latenzy once   -c latenzy.yaml   # one probe cycle, human-readable results
latenzy run    -c latenzy.yaml   # probe on an interval + serve /metrics
```

`latenzy once` prints a per-model table; `latenzy run` serves Prometheus metrics
on `http://127.0.0.1:9877/metrics`. Point Prometheus at it and import the
[dashboard](dashboards.md).

No existing Prometheus/Grafana? The [standalone bundle](standalone.md) runs the
whole stack with one command.
