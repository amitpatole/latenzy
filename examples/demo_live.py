"""Passive live-traffic instrumentation demo — no API key required.

Simulates two "real" application LLM calls (a fast small one and a slower large
one), records them with latenzy's LiveRecorder under source="live", and prints
the resulting Prometheus metrics — the same metric names the synthetic prober
emits, so both show up on one dashboard.

Run it:

    python examples/demo_live.py
"""

from __future__ import annotations

import time

from prometheus_client import CollectorRegistry, generate_latest

from latenzy import LiveRecorder, Metrics, classify_prompt, measure_stream


def fake_llm_stream(text: str, chunk_delay: float, first_token_delay: float):
    """Stand-in for a streaming LLM response (no network, no key)."""
    time.sleep(first_token_delay)
    for word in text.split():
        time.sleep(chunk_delay)
        yield word + " "


def main() -> None:
    registry = CollectorRegistry()
    recorder = LiveRecorder(Metrics(registry))

    calls = [
        ("gpt-4o", "small prompt", "Blue light scatters more.", 0.05, 0.005),
        ("gpt-4o", "x" * 12000, "This one had a large prompt and streamed slower.", 0.30, 0.02),
    ]

    for model, prompt, answer, first_delay, chunk_delay in calls:
        prompt_class = classify_prompt(text=prompt)
        with recorder.observe(provider="openai", model=model, prompt_class=prompt_class) as obs:
            tokens = 0
            for _ in measure_stream(fake_llm_stream(answer, chunk_delay, first_delay), obs):
                tokens += 1
            obs.output_tokens = tokens
        print(
            f"recorded live call: model={model} prompt_class={prompt_class.value} tokens={tokens}"
        )

    print("\n--- /metrics (live source) ---")
    for line in generate_latest(registry).decode().splitlines():
        if 'source="live"' in line and ("ttft" in line or "probes_total" in line):
            print(line)


if __name__ == "__main__":
    main()
