from __future__ import annotations

from latenzy.config import ProviderKind
from latenzy.providers.anthropic import AnthropicProbe
from latenzy.providers.base import ProviderProbe
from latenzy.providers.gemini import GeminiProbe
from latenzy.providers.openai import OpenAIProbe

PROBE_CLASSES: dict[ProviderKind, type[ProviderProbe]] = {
    ProviderKind.anthropic: AnthropicProbe,
    ProviderKind.openai: OpenAIProbe,
    ProviderKind.gemini: GeminiProbe,
}

__all__ = ["PROBE_CLASSES", "AnthropicProbe", "GeminiProbe", "OpenAIProbe", "ProviderProbe"]
