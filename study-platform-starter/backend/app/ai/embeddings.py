"""Embedding adapter for OpenAI-compatible ``/embeddings`` APIs.

Configured independently from the chat model. Verifies vector dimensions and
normalizes provider errors. Never logs input text.
"""

from __future__ import annotations

import time

import httpx

from app.ai.base import (
    AIProviderError,
    EmbeddingDimensionError,
    EmbeddingResult,
    ProviderUnavailable,
    Usage,
)

RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}


class OpenAICompatibleEmbeddingModel:
    def __init__(
        self,
        *,
        api_key: str,
        model_id: str,
        base_url: str,
        dimensions: int | None = None,
        timeout_seconds: float = 60.0,
        max_retries: int = 3,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise ProviderUnavailable("Embedding API key is not configured.")
        self.model_id = model_id
        self.dimensions = dimensions
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._max_retries = max(0, max_retries)
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self._owns_client = client is None
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def embed(self, texts: list[str], *, model: str | None = None) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(vectors=[], model=model or self.model_id, dimensions=self.dimensions or 0)
        payload: dict[str, object] = {"model": model or self.model_id, "input": texts}
        if self.dimensions is not None:
            payload["dimensions"] = self.dimensions
        response = self._post_with_retry("/embeddings", payload)
        try:
            data = response.json()
            ordered = sorted(data["data"], key=lambda item: item.get("index", 0))
            vectors = [item["embedding"] for item in ordered]
        except (KeyError, TypeError, ValueError) as exc:
            raise AIProviderError("Unexpected embeddings response shape.") from exc

        if not vectors:
            raise AIProviderError("Embeddings response contained no vectors.")
        actual_dim = len(vectors[0])
        if self.dimensions is not None and actual_dim != self.dimensions:
            raise EmbeddingDimensionError(
                f"Embedding dimension mismatch: configured {self.dimensions}, received {actual_dim}."
            )
        for vector in vectors:
            if len(vector) != actual_dim:
                raise EmbeddingDimensionError("Inconsistent embedding dimensions in response.")

        usage_block = data.get("usage") or {}
        usage = Usage(input_tokens=int(usage_block.get("prompt_tokens", 0) or 0))
        return EmbeddingResult(
            vectors=[list(map(float, vector)) for vector in vectors],
            model=data.get("model", model or self.model_id),
            dimensions=actual_dim,
            usage=usage,
        )

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
                raise AIProviderError("Embedding provider request failed.") from exc

            if response.status_code in RETRYABLE_STATUS and attempt < self._max_retries:
                time.sleep(min(2**attempt, 8))
                continue
            if response.status_code >= 400:
                raise AIProviderError(f"Embedding provider returned status {response.status_code}.")
            return response

        raise AIProviderError("Embedding provider request failed after retries.") from last_error

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


__all__ = ["OpenAICompatibleEmbeddingModel"]
