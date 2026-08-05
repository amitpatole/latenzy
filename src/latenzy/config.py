"""Configuration models. API keys are resolved from environment variables only —
they have no place in a config file that gets committed or mounted."""

from __future__ import annotations

import enum
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

# Model ids land in URL paths and Prometheus labels; endpoint is a label.
# Restricting the charset keeps hostile config values out of both sinks.
_MODEL_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_ENDPOINT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
# POSIX env-var name; also keeps control/ANSI chars out of doctor output.
_ENV_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")
# Hostname or IP literal; excludes whitespace/control/ANSI in exporter output.
_HOST_RE = re.compile(r"[A-Za-z0-9_.:\[\]-]{1,255}")
# Provider label shares the endpoint charset (short lowercase identifier).
_PROVIDER_RE = _ENDPOINT_RE


def ensure_metric_label(value: str, kind: str) -> str:
    """Validate a value used as a Prometheus label (model/endpoint/provider).

    The live-traffic API accepts these from a host application, so bounding the
    charset here keeps attacker/user-derived values from exploding metric
    cardinality or injecting control chars — the same guarantee config gives.
    """
    pattern = {"model": _MODEL_ID_RE, "endpoint": _ENDPOINT_RE, "provider": _PROVIDER_RE}[kind]
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f"invalid {kind} label {value!r}")
    return value


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
    def _valid_model_ids(cls, v: list[str]) -> list[str]:
        for model in v:
            if not _MODEL_ID_RE.fullmatch(model):
                raise ValueError(
                    f"invalid model id {model!r}: allowed characters are "
                    "letters, digits, and . _ : - (max 128)"
                )
        return v

    @field_validator("endpoint")
    @classmethod
    def _valid_endpoint(cls, v: str) -> str:
        if not _ENDPOINT_RE.fullmatch(v):
            raise ValueError(
                f"invalid endpoint label {v!r}: allowed characters are "
                "letters, digits, and . _ - (max 64)"
            )
        return v

    @field_validator("api_key_env")
    @classmethod
    def _valid_api_key_env(cls, v: str | None) -> str | None:
        if v is not None and not _ENV_NAME_RE.fullmatch(v):
            raise ValueError(f"invalid api_key_env {v!r}: must be a POSIX env-var name")
        return v

    @field_validator("base_url")
    @classmethod
    def _valid_base_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(f"base_url must be an http(s) URL with a host, got {v!r}")
        if parsed.query or parsed.fragment:
            raise ValueError("base_url must not contain a query string or fragment")
        return v.rstrip("/")

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

    @field_validator("host")
    @classmethod
    def _valid_host(cls, v: str) -> str:
        if not _HOST_RE.fullmatch(v):
            raise ValueError(f"invalid host {v!r}: must be a hostname or IP literal")
        return v

    @field_validator("auth_token_env")
    @classmethod
    def _valid_auth_token_env(cls, v: str | None) -> str | None:
        if v is not None and not _ENV_NAME_RE.fullmatch(v):
            raise ValueError(f"invalid auth_token_env {v!r}: must be a POSIX env-var name")
        return v


class OTelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    # None with enabled=true → export to the console (local verification).
    endpoint: str | None = None

    @field_validator("endpoint")
    @classmethod
    def _valid_endpoint(cls, v: str | None) -> str | None:
        if v is None:
            return None
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(f"otel.endpoint must be an http(s) URL with a host, got {v!r}")
        return v


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    providers: list[ProviderConfig] = Field(min_length=1)
    probe: ProbeConfig = Field(default_factory=ProbeConfig)
    exporter: ExporterConfig = Field(default_factory=ExporterConfig)
    otel: OTelConfig = Field(default_factory=OTelConfig)


def load_config(path: str | Path) -> Config:
    raw = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ConfigError(f"config file {path} must contain a YAML mapping")
    return Config.model_validate(data)
