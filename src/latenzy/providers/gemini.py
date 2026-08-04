from __future__ import annotations

from typing import Any

from latenzy.providers.base import ProviderProbe, RequestSpec, StreamEvent, sane_token_count


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
        candidates = data.get("candidates")
        if isinstance(candidates, list) and candidates and isinstance(candidates[0], dict):
            content = candidates[0].get("content")
            parts = content.get("parts") if isinstance(content, dict) else None
            if isinstance(parts, list) and any(
                isinstance(p, dict) and p.get("text") for p in parts
            ):
                has_token = True
        usage = data.get("usageMetadata")
        tokens = (
            sane_token_count(usage.get("candidatesTokenCount")) if isinstance(usage, dict) else None
        )
        return StreamEvent(has_token=has_token, output_tokens=tokens)
