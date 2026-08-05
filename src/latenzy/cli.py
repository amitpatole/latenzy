from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

from latenzy import __version__
from latenzy.config import Config, ConfigError, load_config
from latenzy.exporter import MetricsServer
from latenzy.metrics import Metrics
from latenzy.prober import Prober
from latenzy.sink import FanoutSink, RecordSink


def _fmt(value: float | None, suffix: str = "s") -> str:
    return f"{value:.3f}{suffix}" if value is not None else "-"


async def _once(config: Config) -> int:
    from prometheus_client import CollectorRegistry

    prober = Prober(config, Metrics(CollectorRegistry()))
    try:
        results = await prober.run_once()
    finally:
        await prober.aclose()
    width = max(len(f"{r.provider}/{r.model}") for r in results)
    for r in sorted(results, key=lambda r: (r.provider, r.model, r.prompt_class)):
        tps = f"{r.tokens_per_second:.1f} tok/s" if r.tokens_per_second else "-"
        print(
            f"{r.provider + '/' + r.model:<{width}}  {r.prompt_class:<6}  "
            f"{r.outcome.value:<12}  ttft={_fmt(r.ttft_seconds):<9} "
            f"total={_fmt(r.duration_seconds):<9} {tps}"
        )
    return 0 if all(r.outcome.value == "ok" for r in results) else 1


async def _run(config: Config) -> int:
    log = logging.getLogger("latenzy")
    metrics = Metrics()
    sink: RecordSink = metrics
    if config.otel.enabled:
        from latenzy.otel import OTelBridge, build_meter_provider

        provider = build_meter_provider(config.otel.endpoint)
        sink = FanoutSink(metrics, OTelBridge(provider.get_meter("latenzy")))
        log.info("OpenTelemetry export enabled (%s)", config.otel.endpoint or "console")
    server = MetricsServer(config.exporter, metrics.registry)
    server.start()
    log.info("serving /metrics on %s:%d", config.exporter.host, server.port)
    prober = Prober(config, sink)
    try:
        await prober.run_forever()
    finally:
        await prober.aclose()
        server.close()
    return 0


def _doctor(config: Config) -> int:
    failures = 0
    for provider_cfg in config.providers:
        env = provider_cfg.resolved_api_key_env
        present = bool(os.environ.get(env))
        status = "ok" if present else "MISSING"
        if not present:
            failures += 1
        print(
            f"{provider_cfg.provider.value:<10} endpoint={provider_cfg.endpoint:<12} "
            f"models={len(provider_cfg.models):<3} key({env})={status}"
        )
    try:
        from latenzy.exporter import resolve_auth_token

        resolve_auth_token(config.exporter)
        print(f"exporter   {config.exporter.host}:{config.exporter.port} ok")
    except ConfigError as exc:
        failures += 1
        print(f"exporter   FAIL: {exc}")
    print("doctor: all good" if failures == 0 else f"doctor: {failures} problem(s)")
    return 0 if failures == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="latenzy", description="Per-model LLM latency monitoring")
    parser.add_argument("--version", action="version", version=f"latenzy {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("run", "run the prober and serve /metrics"),
        ("once", "run a single probe cycle and print results"),
        ("doctor", "validate config and check API keys are present"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("-c", "--config", required=True, help="path to latenzy YAML config")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    try:
        config = load_config(args.config)
        if args.command == "doctor":
            return _doctor(config)
        if args.command == "once":
            return asyncio.run(_once(config))
        return asyncio.run(_run(config))
    except ConfigError as exc:
        print(f"latenzy: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
