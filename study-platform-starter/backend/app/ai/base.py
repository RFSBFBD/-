"""Provider-agnostic AI interfaces.

Concrete adapters live beside this module. Application code depends only on
these protocols so models can be swapped by configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


class AIProviderError(RuntimeError):
    """Base class for provider failures (network, auth, rate limit)."""


class ProviderUnavailable(AIProviderError):
    """Raised when a required provider is not configured."""


class EmbeddingDimensionError(AIProviderError):
    pass


@dataclass(frozen=True)
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float | None = None


@dataclass(frozen=True)
class ChatResult:
    content: str
    model: str
    usage: Usage = field(default_factory=Usage)


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]
    model: str
    dimensions: int
    usage: Usage = field(default_factory=Usage)


@dataclass(frozen=True)
class RankedDocument:
    chunk_id: Any
    material_id: Any
    subject_id: Any
    content: str
    score: float
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedPage:
    page_number: int | None
    text: str
    start_ms: int | None = None
    end_ms: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedDocument:
    pages: list[ParsedPage]
    parser: str

    @property
    def text(self) -> str:
        return "\n\n".join(page.text for page in self.pages if page.text.strip())


@runtime_checkable
class ChatModel(Protocol):
    model_id: str

    def generate(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> ChatResult: ...


@runtime_checkable
class EmbeddingModel(Protocol):
    model_id: str
    dimensions: int | None

    def embed(self, texts: list[str], *, model: str | None = None) -> EmbeddingResult: ...


@runtime_checkable
class Reranker(Protocol):
    def rank(self, query: str, passages: list[str], *, top_k: int) -> list[int]: ...


@runtime_checkable
class TranscriptionProvider(Protocol):
    def transcribe(
        self, data: bytes, *, filename: str, language: str | None = None
    ) -> list[ParsedPage]: ...


@runtime_checkable
class DocumentParser(Protocol):
    def parse(self, data: bytes, *, mime_type: str, filename: str) -> ParsedDocument: ...


@runtime_checkable
class VectorStore(Protocol):
    def upsert(self, chunks: list["VectorChunk"]) -> int: ...

    def search(self, *, subject_id: Any, query_vector: list[float], top_k: int) -> list[RankedDocument]: ...


@dataclass(frozen=True)
class VectorChunk:
    material_id: Any
    subject_id: Any
    chunk_index: int
    content: str
    content_hash: str
    embedding: list[float]
    token_count: int
    model_version: str
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "AIProviderError",
    "ChatMessage",
    "ChatModel",
    "ChatResult",
    "DocumentParser",
    "EmbeddingDimensionError",
    "EmbeddingModel",
    "EmbeddingResult",
    "ParsedDocument",
    "ParsedPage",
    "ProviderUnavailable",
    "RankedDocument",
    "Reranker",
    "TranscriptionProvider",
    "Usage",
    "VectorChunk",
    "VectorStore",
]
