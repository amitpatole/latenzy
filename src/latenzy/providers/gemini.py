from __future__ import annotations

from typing import Any

from latenzy.providers.base import ProviderProbe, RequestSpec, StreamEvent


class GeminiProbe(ProviderProbe):
    name = "gemini"

    def build_request(self, model: str, prompt: str, max_output_tokens: int) -> RequestSpec:
        return RequestSpec(
            url=(
                f"{self._config.resolved_base_url}/v1beta/models/"
                f"{model}:streamGenerateContent?alt=sse"
            ),
            headers={"x-goog-api-key": self._config.api_key()},
            body={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": max_output_tokens},
            },
        )

    def parse_data(self, data: dict[str, Any]) -> StreamEvent:
        has_token = False
        candidates = data.get("candidates") or []
        if candidates:
            parts = (candidates[0].get("content") or {}).get("parts") or []
            if any(p.get("text") for p in parts):
                has_token = True
        usage = data.get("usageMetadata") or {}
        tokens = usage.get("candidatesTokenCount")
        return StreamEvent(
            has_token=has_token,
            output_tokens=tokens if isinstance(tokens, int) else None,
        )
