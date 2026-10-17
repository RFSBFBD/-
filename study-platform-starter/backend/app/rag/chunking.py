"""Text normalization and chunking for knowledge ingestion.

Splits parsed pages into overlapping character-bounded chunks while preserving
page/timestamp provenance. Uses a character target with a token estimate so we
do not depend on a tokenizer library.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from app.ai.base import ParsedDocument

_WHITESPACE = re.compile(r"[ \t\f\v]+")
_MULTI_NEWLINE = re.compile(r"\n{3,}")
# Sentence-ish boundaries for Arabic and English.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?؟।])\s+|\n+")

_CHARS_PER_TOKEN = 4


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WHITESPACE.sub(" ", text)
    text = _MULTI_NEWLINE.sub("\n\n", text)
    return text.strip()


def estimate_tokens(text: str) -> int:
    """Rough token estimate; documented as an approximation, not exact."""
    if not text:
        return 0
    return max(1, (len(text) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Chunk:
    index: int
    content: str
    content_hash: str
    token_count: int
    provenance: dict[str, Any] = field(default_factory=dict)


def _split_into_pieces(text: str, target_chars: int) -> list[str]:
    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE_SPLIT.split(text):
        sentence = sentence.strip()
        if not sentence:
            continue
        if not current:
            current = sentence
        elif len(current) + 1 + len(sentence) <= target_chars:
            current = f"{current} {sentence}"
        else:
            pieces.append(current)
            current = sentence
    if current:
        pieces.append(current)
    return pieces


def _apply_overlap(pieces: list[str], overlap_chars: int) -> list[str]:
    if overlap_chars <= 0 or len(pieces) <= 1:
        return pieces
    result = [pieces[0]]
    for previous, piece in zip(pieces, pieces[1:]):
        tail = previous[-overlap_chars:]
        result.append(f"{tail} {piece}".strip())
    return result


def chunk_document(
    document: ParsedDocument,
    *,
    target_chars: int,
    overlap_chars: int,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    index = 0
    for page in document.pages:
        text = normalize_text(page.text)
        if not text:
            continue
        pieces = _apply_overlap(_split_into_pieces(text, target_chars), overlap_chars)
        for piece in pieces:
            if not piece.strip():
                continue
            provenance: dict[str, Any] = {}
            if page.page_number is not None:
                provenance["page_number"] = page.page_number
            if page.start_ms is not None:
                provenance["start_ms"] = page.start_ms
            if page.end_ms is not None:
                provenance["end_ms"] = page.end_ms
            chunks.append(
                Chunk(
                    index=index,
                    content=piece,
                    content_hash=content_hash(piece),
                    token_count=estimate_tokens(piece),
                    provenance=provenance,
                )
            )
            index += 1
    return chunks


__all__ = [
    "Chunk",
    "chunk_document",
    "content_hash",
    "estimate_tokens",
    "normalize_text",
]
