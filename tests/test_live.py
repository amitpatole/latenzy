from __future__ import annotations

import pytest
from prometheus_client import CollectorRegistry

from latenzy.config import PromptClass
from latenzy.live import LiveRecorder, classify_prompt, measure_stream
from latenzy.metrics import Metrics

LIVE_OK = {
    "source": "live",
    "provider": "openai",
    "model": "gpt-4o",
    "endpoint": "live",
    "prompt_class": "small",
}


def test_classify_prompt_by_tokens() -> None:
    assert classify_prompt(tokens=10) is PromptClass.small
    assert classify_prompt(tokens=200) is PromptClass.small
    assert classify_prompt(tokens=201) is PromptClass.medium
    assert classify_prompt(tokens=2000) is PromptClass.medium
    assert classify_prompt(tokens=2001) is PromptClass.large


def test_classify_prompt_by_text() -> None:
    assert classify_prompt(text="hi") is PromptClass.small
    assert classify_prompt(text="x" * 20000) is PromptClass.large


def test_classify_prompt_requires_input() -> None:
    with pytest.raises(ValueError):
        classify_prompt()


def test_live_observation_records_under_source_live(
    registry: CollectorRegistry, metrics: Metrics
) -> None:
    recorder = LiveRecorder(metrics)
    with recorder.observe(provider="openai", model="gpt-4o", prompt_class=PromptClass.small) as obs:
        obs.first_token()
        obs.output_tokens = 12
    assert registry.get_sample_value("latenzy_probes_total", {**LIVE_OK, "outcome": "ok"}) == 1
    assert registry.get_sample_value("latenzy_ttft_seconds_count", LIVE_OK) == 1
    assert registry.get_sample_value("latenzy_last_success_timestamp_seconds", LIVE_OK) is not None


def test_live_no_first_token_is_error(registry: CollectorRegistry, metrics: Metrics) -> None:
    recorder = LiveRecorder(metrics)
    with recorder.observe(provider="openai", model="gpt-4o", prompt_class=PromptClass.small):
        pass  # never marked first_token
    assert registry.get_sample_value("latenzy_probes_total", {**LIVE_OK, "outcome": "error"}) == 1
    assert registry.get_sample_value("latenzy_ttft_seconds_count", LIVE_OK) is None


def test_live_exception_records_error_and_reraises(
    registry: CollectorRegistry, metrics: Metrics
) -> None:
    recorder = LiveRecorder(metrics)
    with pytest.raises(RuntimeError):  # noqa: SIM117
        with recorder.observe(
            provider="openai", model="gpt-4o", prompt_class=PromptClass.small
        ) as obs:
            obs.first_token()
            raise RuntimeError("boom")
    assert registry.get_sample_value("latenzy_probes_total", {**LIVE_OK, "outcome": "error"}) == 1


def test_live_rejects_hostile_labels(metrics: Metrics) -> None:
    recorder = LiveRecorder(metrics)
    for bad in [
        {"provider": "openai", "model": "../etc/passwd", "prompt_class": PromptClass.small},
        {"provider": "bad prov", "model": "gpt-4o", "prompt_class": PromptClass.small},
    ]:
        with pytest.raises(ValueError):  # noqa: SIM117
            with recorder.observe(**bad):  # type: ignore[arg-type]
                pass


def test_live_absurd_token_count_bounded(registry: CollectorRegistry, metrics: Metrics) -> None:
    recorder = LiveRecorder(metrics)
    with recorder.observe(provider="openai", model="gpt-4o", prompt_class=PromptClass.small) as obs:
        obs.first_token()
        obs.output_tokens = 10**400  # would overflow tokens/sec
    # Recorded as ok, but the implausible token count is dropped (no tps observed).
    assert registry.get_sample_value("latenzy_probes_total", {**LIVE_OK, "outcome": "ok"}) == 1
    assert registry.get_sample_value("latenzy_output_tokens_per_second_count", LIVE_OK) is None


def test_measure_stream_marks_first_token(registry: CollectorRegistry, metrics: Metrics) -> None:
    recorder = LiveRecorder(metrics)
    with recorder.observe(provider="openai", model="gpt-4o", prompt_class=PromptClass.small) as obs:
        collected = list(measure_stream(iter(["", "Hello", " world"]), obs))
        obs.output_tokens = 2
    assert collected == ["", "Hello", " world"]
    assert registry.get_sample_value("latenzy_ttft_seconds_count", LIVE_OK) == 1
