"""Chat completion adapter for OpenAI-compatible ``/chat/completions`` APIs.

Works with any OpenAI-compatible provider (OpenRouter, Google Gemini, Groq, ...);
the provider is selected purely by configuration. Implements bounded retry with
exponential backoff, timeouts, usage extraction, and provider error
normalization. Never logs prompt content.
"""

from __future__ import annotations

import time

import httpx

from app.ai.base import (
    AIProviderError,
    ChatMessage,
    ChatResult,
    ProviderUnavailable,
    Usage,
)

RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}


class OpenRouterChatModel:
    def __init__(
        self,
        *,
        api_key: str,
        model_id: str,
        base_url: str,
        site_url: str = "",
        app_name: str = "",
        timeout_seconds: float = 60.0,
        max_retries: int = 3,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise ProviderUnavailable("Chat API key is not configured.")
        self.model_id = model_id
        self._base_url = base_url.rstrip("/")
        self._site_url = site_url
        self._app_name = app_name
        self._timeout = timeout_seconds
        self._max_retries = max(0, max_retries)
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self._owns_client = client is None
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if site_url:
            self._headers["HTTP-Referer"] = site_url
        if app_name:
            self._headers["X-Title"] = app_name

    def generate(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> ChatResult:
        payload: dict[str, object] = {
            "model": model or self.model_id,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature

        response = self._post_with_retry("/chat/completions", payload)
        try:
            data = response.json()
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AIProviderError("Unexpected chat response shape.") from exc

        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise AIProviderError("Chat provider returned no text content.")

        usage_block = data.get("usage") or {}
        usage = Usage(
            input_tokens=int(usage_block.get("prompt_tokens", 0) or 0),
            output_tokens=int(usage_block.get("completion_tokens", 0) or 0),
        )
        return ChatResult(content=content, model=data.get("model", model or self.model_id), usage=usage)

    def _post_with_retry(self, path: str, payload: dict[str, object]) -> httpx.Response:
        url = f"{self._base_url}{path}"
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.post(url, headers=self._headers, json=payload, timeout=self._timeout)
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < self._max_retries:
                    time.sleep(min(2**attempt, 8))
                    continue
                raise AIProviderError("Chat provider request failed.") from exc

            if response.status_code in RETRYABLE_STATUS and attempt < self._max_retries:
                time.sleep(min(2**attempt, 8))
                continue
            if response.status_code >= 400:
                raise AIProviderError(f"Chat provider returned status {response.status_code}.")
            return response

        raise AIProviderError("Chat provider request failed after retries.") from last_error

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


__all__ = ["OpenRouterChatModel"]
