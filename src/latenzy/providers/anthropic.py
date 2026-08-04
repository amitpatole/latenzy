from __future__ import annotations

from typing import Any

from latenzy.providers.base import ProviderProbe, RequestSpec, StreamEvent


class AnthropicProbe(ProviderProbe):
    name = "anthropic"

    def build_request(self, model: str, prompt: str, max_output_tokens: int) -> RequestSpec:
        return RequestSpec(
            url=f"{self._config.resolved_base_url}/v1/messages",
            headers={
                "x-api-key": self._config.api_key(),
                "anthropic-version": "2023-06-01",
            },
            body={
                "model": model,
                "max_tokens": max_output_tokens,
                "stream": True,
                "messages": [{"role": "user", "content": prompt}],
            },
        )

    def parse_data(self, data: dict[str, Any]) -> StreamEvent:
        kind = data.get("type")
        if kind == "content_block_delta":
            return StreamEvent(has_token=True)
        if kind == "message_delta":
            usage = data.get("usage") or {}
            tokens = usage.get("output_tokens")
            if isinstance(tokens, int):
                return StreamEvent(output_tokens=tokens)
        return StreamEvent()
