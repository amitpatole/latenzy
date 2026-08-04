"""Configuration models. API keys are resolved from environment variables only —
they have no place in a config file that gets committed or mounted."""

from __future__ import annotations

import enum
import os
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConfigError(ValueError):
    """Raised when configuration is invalid or a required secret is missing."""


class ProviderKind(str, enum.Enum):
    anthropic = "anthropic"
    openai = "openai"
    gemini = "gemini"


class PromptClass(str, enum.Enum):
    small = "small"
    medium = "medium"
    large = "large"


DEFAULT_API_KEY_ENV: dict[ProviderKind, str] = {
    ProviderKind.anthropic: "ANTHROPIC_API_KEY",
    ProviderKind.openai: "OPENAI_API_KEY",
    ProviderKind.gemini: "GEMINI_API_KEY",
}

DEFAULT_BASE_URL: dict[ProviderKind, str] = {
    ProviderKind.anthropic: "https://api.anthropic.com",
    ProviderKind.openai: "https://api.openai.com",
    ProviderKind.gemini: "https://generativelanguage.googleapis.com",
}


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: ProviderKind
    models: list[str] = Field(min_length=1)
    endpoint: str = "direct"
    base_url: str | None = None
    api_key_env: str | None = None

    @field_validator("models")
    @classmethod
    def _no_blank_models(cls, v: list[str]) -> list[str]:
        if any(not m.strip() for m in v):
            raise ValueError("model ids must be non-empty")
        return v

    @property
    def resolved_base_url(self) -> str:
        return self.base_url or DEFAULT_BASE_URL[self.provider]

    @property
    def resolved_api_key_env(self) -> str:
        return self.api_key_env or DEFAULT_API_KEY_ENV[self.provider]

    def api_key(self) -> str:
        env = self.resolved_api_key_env
        key = os.environ.get(env, "")
        if not key:
            raise ConfigError(
                f"missing API key for provider '{self.provider.value}': "
                f"environment variable {env} is not set"
            )
        return key


class ProbeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interval_seconds: float = Field(default=300.0, ge=10.0)
    timeout_seconds: float = Field(default=60.0, ge=1.0, le=600.0)
    max_output_tokens: int = Field(default=16, ge=1, le=1024)
    prompt_classes: list[PromptClass] = Field(default_factory=lambda: [PromptClass.small])
    concurrency: int = Field(default=4, ge=1, le=32)


class ExporterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = "127.0.0.1"
    port: int = Field(default=9877, ge=0, le=65535)
    auth_token_env: str | None = None


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    providers: list[ProviderConfig] = Field(min_length=1)
    probe: ProbeConfig = Field(default_factory=ProbeConfig)
    exporter: ExporterConfig = Field(default_factory=ExporterConfig)


def load_config(path: str | Path) -> Config:
    raw = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ConfigError(f"config file {path} must contain a YAML mapping")
    return Config.model_validate(data)
