# API reference

The public API is re-exported from the top-level `latenzy` package.

## Live-traffic instrumentation

::: latenzy.live.LiveRecorder

::: latenzy.live.LiveObservation

::: latenzy.live.classify_prompt

::: latenzy.live.measure_stream

## Metrics & sinks

::: latenzy.metrics.Metrics

::: latenzy.sink.RecordSink

::: latenzy.sink.FanoutSink

## OpenTelemetry bridge

Requires the `otel` extra (`pip install 'latenzy[otel]'`).

::: latenzy.otel.OTelBridge

::: latenzy.otel.build_meter_provider

## Configuration models

::: latenzy.config.Config

::: latenzy.config.ProviderConfig

::: latenzy.config.ProbeConfig

::: latenzy.config.ExporterConfig

::: latenzy.config.load_config

## Probe result

::: latenzy.probe.ProbeResult

::: latenzy.probe.Outcome
