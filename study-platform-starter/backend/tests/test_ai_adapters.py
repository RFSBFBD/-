"""Unit tests for the OpenAI-compatible AI adapters.

These tests exercise the request/response contract of the embedding and chat
adapters (including the ``dimensions`` parameter used by Gemini embeddings)
without making any network calls.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.ai.base import AIProviderError, EmbeddingDimensionError
from app.ai.embeddings import OpenAICompatibleEmbeddingModel
from app.ai.openrouter_chat import OpenRouterChatModel


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_embedding_sends_dimensions_and_returns_vector():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={
                "model": "gemini-embedding-001",
                "data": [{"index": 0, "embedding": [0.0] * 1536}],
                "usage": {"prompt_tokens": 3},
            },
        )

    model = OpenAICompatibleEmbeddingModel(
        api_key="test-key",
        model_id="gemini-embedding-001",
        base_url="https://example.test/v1beta/openai",
        dimensions=1536,
        client=_client(handler),
    )

    result = model.embed(["hello"])

    assert captured["url"] == "https://example.test/v1beta/openai/embeddings"
    assert captured["body"]["dimensions"] == 1536
    assert captured["body"]["model"] == "gemini-embedding-001"
    assert captured["auth"] == "Bearer test-key"
    assert result.dimensions == 1536
    assert len(result.vectors[0]) == 1536


def test_embedding_omits_dimensions_when_not_configured():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"model": "m", "data": [{"index": 0, "embedding": [0.0] * 8}]},
        )

    model = OpenAICompatibleEmbeddingModel(
        api_key="test-key",
        model_id="m",
        base_url="https://example.test/v1",
        client=_client(handler),
    )
    model.embed(["hello"])

    assert "dimensions" not in captured["body"]


def test_embedding_dimension_mismatch_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"model": "m", "data": [{"index": 0, "embedding": [0.0] * 3072}]},
        )

    model = OpenAICompatibleEmbeddingModel(
        api_key="test-key",
        model_id="m",
        base_url="https://example.test/v1",
        dimensions=1536,
        client=_client(handler),
    )

    with pytest.raises(EmbeddingDimensionError):
        model.embed(["hello"])


def test_embedding_provider_error_is_normalized():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "bad"}})

    model = OpenAICompatibleEmbeddingModel(
        api_key="test-key",
        model_id="m",
        base_url="https://example.test/v1",
        max_retries=0,
        client=_client(handler),
    )

    with pytest.raises(AIProviderError):
        model.embed(["hello"])


def test_chat_parses_content_and_usage():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "gemini-flash-latest",
                "choices": [{"message": {"role": "assistant", "content": "OK"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 1},
            },
        )

    model = OpenRouterChatModel(
        api_key="test-key",
        model_id="gemini-flash-latest",
        base_url="https://example.test/v1beta/openai",
        client=_client(handler),
    )

    from app.ai.base import ChatMessage

    result = model.generate(
        [ChatMessage(role="user", content="hi")], max_tokens=64, temperature=0.2
    )

    assert captured["url"] == "https://example.test/v1beta/openai/chat/completions"
    assert captured["body"]["model"] == "gemini-flash-latest"
    assert captured["body"]["max_tokens"] == 64
    assert result.content == "OK"
    assert result.usage.input_tokens == 5
    assert result.usage.output_tokens == 1
