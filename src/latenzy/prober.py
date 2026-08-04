"""Probe scheduler: fans out one probe per (provider, model, prompt_class) with
bounded concurrency, records results, and repeats on a fixed interval."""

from __future__ import annotations

import asyncio
import contextlib
import logging

import httpx

from latenzy.config import Config, PromptClass
from latenzy.metrics import Metrics
from latenzy.probe import PROMPTS, ProbeResult
from latenzy.providers import PROBE_CLASSES
from latenzy.providers.base import ProviderProbe

logger = logging.getLogger("latenzy")


class Prober:
    def __init__(
        self,
        config: Config,
        metrics: Metrics,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config
        self._metrics = metrics
        self._client = httpx.AsyncClient(transport=transport)
        self._probes: list[tuple[ProviderProbe, str, str]] = []
        for provider_cfg in config.providers:
            probe = PROBE_CLASSES[provider_cfg.provider](provider_cfg, self._client)
            for model in provider_cfg.models:
                for prompt_class in config.probe.prompt_classes:
                    self._probes.append((probe, model, prompt_class.value))

    async def aclose(self) -> None:
        await self._client.aclose()

    async def run_once(self) -> list[ProbeResult]:
        semaphore = asyncio.Semaphore(self._config.probe.concurrency)
        probe_cfg = self._config.probe

        async def one(probe: ProviderProbe, model: str, prompt_class: str) -> ProbeResult:
            async with semaphore:
                result = await probe.probe(
                    model=model,
                    prompt_class=prompt_class,
                    prompt=PROMPTS[PromptClass(prompt_class)],
                    max_output_tokens=probe_cfg.max_output_tokens,
                    timeout=probe_cfg.timeout_seconds,
                )
            self._metrics.record(result)
            return result

        return list(await asyncio.gather(*(one(p, m, c) for p, m, c in self._probes)))

    async def run_forever(self, stop: asyncio.Event | None = None) -> None:
        stop = stop or asyncio.Event()
        while not stop.is_set():
            results = await self.run_once()
            ok = sum(1 for r in results if r.outcome.value == "ok")
            logger.info("probe cycle complete: %d/%d ok", ok, len(results))
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self._config.probe.interval_seconds)
