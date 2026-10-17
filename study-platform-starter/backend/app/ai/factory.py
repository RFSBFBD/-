"""AI provider factory.

Adapters are built from configuration and cached. Missing providers raise
``ProviderUnavailable`` so callers can return safe "unavailable" states.
"""

from __future__ import annotations

from functools import lru_cache

from app.ai.base import (
    AIProviderError,
    ChatModel,
    EmbeddingModel,
    ProviderUnavailable,
    Reranker,
    TranscriptionProvider,
)
from app.ai.embeddings import OpenAICompatibleEmbeddingModel
from app.ai.openrouter_chat import OpenRouterChatModel
from app.ai.transcription import LocalWhisperTranscriptionProvider
from app.config import settings


@lru_cache(maxsize=1)
def get_chat_model() -> ChatModel:
    if not settings.ai_api_key or not settings.ai_chat_model:
        raise ProviderUnavailable("Chat model is not configured (AI_API_KEY, AI_CHAT_MODEL).")
    return OpenRouterChatModel(
        api_key=settings.ai_api_key,
        model_id=settings.ai_chat_model,
        base_url=settings.ai_base_url,
        site_url=settings.ai_site_url,
        app_name=settings.ai_app_name,
        timeout_seconds=settings.ai_request_timeout_seconds,
        max_retries=settings.ai_max_retries,
    )


@lru_cache(maxsize=1)
def get_embedding_model() -> EmbeddingModel:
    if not settings.embedding_api_key or not settings.embedding_model:
        raise ProviderUnavailable("Embedding model is not configured (EMBEDDING_API_KEY, EMBEDDING_MODEL).")
    return OpenAICompatibleEmbeddingModel(
        api_key=settings.embedding_api_key,
        model_id=settings.embedding_model,
        base_url=settings.embedding_base_url,
        dimensions=settings.embedding_dimensions,
        timeout_seconds=settings.ai_request_timeout_seconds,
        max_retries=settings.ai_max_retries,
    )


def get_reranker() -> Reranker | None:
    """Optional; disabled unless a reranker is configured in a later phase."""
    return None


@lru_cache(maxsize=1)
def get_transcription_provider() -> TranscriptionProvider:
    provider = settings.transcription_provider
    if provider in {"", "none"}:
        raise ProviderUnavailable(
            "Transcription is not configured (set TRANSCRIPTION_PROVIDER=local)."
        )
    if provider == "local":
        return LocalWhisperTranscriptionProvider(
            model_size=settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
    raise ProviderUnavailable(f"Unsupported transcription provider '{provider}'.")


__all__ = [
    "AIProviderError",
    "get_chat_model",
    "get_embedding_model",
    "get_reranker",
    "get_transcription_provider",
]
