# Configuration

latenzy is configured with a YAML file (`-c/--config`). It has three sections:
`providers`, `probe`, and `exporter`. **API keys are read from environment
variables only** and are rejected if placed in the config.

## `providers` (required, ≥1)

Each entry describes one provider and the models to probe on it.

| Field | Default | Meaning |
|---|---|---|
| `provider` | — | `anthropic`, `openai`, or `gemini` |
| `models` | — | list of model IDs (≥1); charset-validated |
| `endpoint` | `direct` | free label distinguishing the path (`direct` / `bedrock-us-east-1` / `vertex` / a gateway) — separates the same model over different routes |
| `base_url` | provider default | override the API base; must be an `http(s)` URL with a host, no query/fragment |
| `api_key_env` | per provider | env var holding the key (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` by default) |

## `probe`

| Field | Default | Bounds | Meaning |
|---|---|---|---|
| `interval_seconds` | `300` | ≥10 | delay between probe cycles |
| `timeout_seconds` | `60` | 1–600 | per-probe overall deadline |
| `max_output_tokens` | `16` | 1–1024 | cap on generated tokens per probe (keeps cost negligible) |
| `prompt_classes` | `[small]` | — | any of `small`, `medium`, `large`; latency scales with input size |
| `concurrency` | `4` | 1–32 | max simultaneous in-flight probes |

## `exporter`

| Field | Default | Meaning |
|---|---|---|
| `host` | `127.0.0.1` | bind address; hostname/IP literal |
| `port` | `9877` | bind port |
| `auth_token_env` | none | env var holding a bearer token |

**Fail-closed rule:** binding a non-loopback `host` **without** `auth_token_env`
refuses to start. Loopback is zero-config; any routable bind requires a token,
which Prometheus then sends as `Authorization: Bearer <token>`. See
[Security](security.md).

## Endpoints and model snapshots

`endpoint` is a first-class label so you can compare the *same* model over
different paths (direct API vs Bedrock vs Vertex) — a real routing/procurement
decision. Track dated snapshot IDs (e.g. `claude-haiku-4-5-20251001`) alongside
aliases to catch a silent alias re-point, a common cause of a mystery latency
shift.
