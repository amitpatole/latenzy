from __future__ import annotations

from typing import Any

from latenzy.providers.base import ProviderProbe, RequestSpec, StreamEvent


class OpenAIProbe(ProviderProbe):
    name = "openai"

    def build_request(self, model: str, prompt: str, max_output_tokens: int) -> RequestSpec:
        return RequestSpec(
            url=f"{self._config.resolved_base_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {self._config.api_key()}"},
            body={
                "model": model,
                "max_completion_tokens": max_output_tokens,
                "stream": True,
                "stream_options": {"include_usage": True},
                "messages": [{"role": "user", "content": prompt}],
            },
        )

    def parse_data(self, data: dict[str, Any]) -> StreamEvent:
        has_token = False
        choices = data.get("choices") or []
        if choices:
            delta = choices[0].get("delta") or {}
            if delta.get("content"):
                has_token = True
        usage = data.get("usage") or {}
        tokens = usage.get("completion_tokens")
        return StreamEvent(
            has_token=has_token,
            output_tokens=tokens if isinstance(tokens, int) else None,
        )
