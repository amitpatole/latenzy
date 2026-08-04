from __future__ import annotations

from pathlib import Path

import pytest

from latenzy.config import Config, ConfigError, ProviderConfig, ProviderKind, load_config


def test_defaults_resolved() -> None:
    cfg = ProviderConfig(provider=ProviderKind.anthropic, models=["m"])
    assert cfg.resolved_base_url == "https://api.anthropic.com"
    assert cfg.resolved_api_key_env == "ANTHROPIC_API_KEY"
    assert cfg.endpoint == "direct"


def test_api_key_missing_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cfg = ProviderConfig(provider=ProviderKind.anthropic, models=["m"])
    with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"):
        cfg.api_key()


def test_api_key_never_in_config_schema() -> None:
    # Keys come from the environment only; a literal key field must be rejected.
    with pytest.raises(ValueError):
        ProviderConfig.model_validate({"provider": "openai", "models": ["m"], "api_key": "sk-oops"})


def test_rejects_unknown_provider_and_empty_models() -> None:
    with pytest.raises(ValueError):
        Config.model_validate({"providers": [{"provider": "closedai", "models": ["m"]}]})
    with pytest.raises(ValueError):
        Config.model_validate({"providers": [{"provider": "openai", "models": []}]})
    with pytest.raises(ValueError):
        Config.model_validate({"providers": []})


def test_load_config_yaml(tmp_path: Path) -> None:
    path = tmp_path / "latenzy.yaml"
    path.write_text(
        """
providers:
  - provider: anthropic
    models: [claude-sonnet-4-6, claude-haiku-4-5-20251001]
    endpoint: direct
probe:
  interval_seconds: 60
  prompt_classes: [small, large]
exporter:
  host: 127.0.0.1
  port: 9877
"""
    )
    cfg = load_config(path)
    assert len(cfg.providers[0].models) == 2
    assert [c.value for c in cfg.probe.prompt_classes] == ["small", "large"]


def test_load_config_rejects_non_mapping(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("- just\n- a\n- list\n")
    with pytest.raises(ConfigError):
        load_config(path)
