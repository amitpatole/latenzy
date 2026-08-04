# CLI

All commands take `-c/--config <path>`.

## `latenzy doctor`

Validates the config and checks that each provider's API key is present in the
environment. Prints key **presence** only, never values.

```console
$ latenzy doctor -c latenzy.yaml
anthropic  endpoint=direct       models=2   key(ANTHROPIC_API_KEY)=ok
openai     endpoint=direct       models=2   key(OPENAI_API_KEY)=MISSING
gemini     endpoint=direct       models=1   key(GEMINI_API_KEY)=ok
exporter   127.0.0.1:9877 ok
doctor: 1 problem(s)
```

Exit code is non-zero if any key is missing or the exporter config is invalid.

## `latenzy once`

Runs a single probe cycle and prints a per-model table (TTFT, total latency,
tokens/sec, outcome). Exit code is non-zero if any probe did not return `ok`.
Useful for a one-shot check or a CI smoke test.

## `latenzy run`

Runs the prober on `probe.interval_seconds` and serves Prometheus metrics on
`http://<host>:<port>/metrics`. This is the long-running monitor.

## `latenzy --version`

Prints the installed version.
