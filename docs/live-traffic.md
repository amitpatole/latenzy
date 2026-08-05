# Live traffic

The prober answers "is this model slow right now?" To also chart your **own**
traffic's p95, wrap real LLM calls with `LiveRecorder`. It emits the same metric
names under `source="live"`, so the same [dashboards](dashboards.md) work — no
separate pipeline. The metric semantics follow the OpenTelemetry GenAI
conventions.

## Usage

```python
from latenzy import LiveRecorder, Metrics, classify_prompt, measure_stream

recorder = LiveRecorder(Metrics())  # shares your app's Prometheus registry

with recorder.observe(
    provider="openai",
    model="gpt-4o",
    prompt_class=classify_prompt(text=prompt),
) as obs:
    for chunk in measure_stream(client.stream(prompt), obs):  # marks first-token timing
        handle(chunk)
    obs.output_tokens = n_tokens
```

- `classify_prompt(text=... | tokens=...)` buckets the prompt into
  `small`/`medium`/`large` so live and synthetic latencies are comparable.
- `measure_stream(chunks, obs)` marks `obs.first_token()` on the first non-empty
  chunk; or call `obs.first_token()` yourself.
- A raised exception inside the block is recorded as an `error` outcome and
  re-raised.

## Safety

Label values (`provider`, `model`, `endpoint`) are charset-validated because they
may come from user input — a host app cannot explode metric cardinality or inject
control characters. App-supplied `output_tokens` are sanity-bounded, matching the
prober's hardening.

## OpenTelemetry

`LiveRecorder` (and the prober) take any `RecordSink`. To emit to OpenTelemetry —
on its own or alongside Prometheus — install the `otel` extra and pass an
`OTelBridge` (or a `FanoutSink` of both):

```python
from latenzy import FanoutSink, Metrics, LiveRecorder
from latenzy.otel import OTelBridge  # needs: pip install 'latenzy[otel]'

recorder = LiveRecorder(FanoutSink(Metrics(), OTelBridge(my_meter)))
```

Instrument names follow the OpenTelemetry GenAI conventions
(`gen_ai.client.operation.duration`, `gen_ai.client.token.usage`) with
`gen_ai.system` / `gen_ai.request.model` attributes, so the series line up with
an existing OTel GenAI pipeline. For the standalone `latenzy run`, enable it via
the [`otel` config section](configuration.md#otel-optional) instead.

## Runnable demo

A key-free, copy-paste walkthrough lives in
[`examples/demo_live.py`](https://github.com/amitpatole/latenzy/blob/main/examples/demo_live.py):

```console
$ python examples/demo_live.py
recorded live call: model=gpt-4o prompt_class=small tokens=4
recorded live call: model=gpt-4o prompt_class=large tokens=9

--- /metrics (live source) ---
latenzy_ttft_seconds_count{...,prompt_class="small",...,source="live"} 1.0
latenzy_ttft_seconds_sum{...,prompt_class="small",...,source="live"} 0.0553...
latenzy_ttft_seconds_sum{...,prompt_class="large",...,source="live"} 0.3202...
latenzy_probes_total{...,outcome="ok",prompt_class="small",...,source="live"} 1.0
```

See the [API reference](api.md) for the full signatures.
