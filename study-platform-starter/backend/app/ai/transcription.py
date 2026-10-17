"""Audio transcription providers.

The default adapter runs a local `faster-whisper` model. The heavy dependency is
imported lazily so the rest of the API runs without it, and the adapter is only
selected when ``TRANSCRIPTION_PROVIDER`` is configured.

Providers return timestamped ``ParsedPage`` segments (``start_ms``/``end_ms``)
plus per-segment metadata so callers can preserve timing, confidence, and
language information without depending on a specific engine.
"""

from __future__ import annotations

import math
import os
import tempfile

from app.ai.base import AIProviderError, ParsedPage


class TranscriptionError(AIProviderError):
    """Raised when audio cannot be transcribed (missing engine, bad audio, etc.)."""


class LocalWhisperTranscriptionProvider:
    """faster-whisper adapter. The model is loaded once and reused."""

    name = "local"

    def __init__(self, *, model_size: str, device: str, compute_type: str) -> None:
        self.model_id = f"faster-whisper/{model_size}"
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:  # pragma: no cover - optional dependency
                raise TranscriptionError(
                    "faster-whisper is not installed on this server."
                ) from exc
            try:
                self._model = WhisperModel(
                    self._model_size,
                    device=self._device,
                    compute_type=self._compute_type,
                )
            except Exception as exc:  # noqa: BLE001 - normalize engine errors
                raise TranscriptionError("Failed to load the local Whisper model.") from exc
        return self._model

    def transcribe(
        self, data: bytes, *, filename: str, language: str | None = None
    ) -> list[ParsedPage]:
        if not data:
            raise TranscriptionError("Audio payload is empty.")
        model = self._load()
        suffix = os.path.splitext(filename)[1] or ".audio"
        temp_path: str | None = None
        try:
            fd, temp_path = tempfile.mkstemp(suffix=suffix)
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            try:
                segments, info = model.transcribe(
                    temp_path, language=language or None, vad_filter=True
                )
                detected_language = getattr(info, "language", None)
                pages: list[ParsedPage] = []
                for segment in segments:
                    text = (segment.text or "").strip()
                    if not text:
                        continue
                    start_ms = _to_ms(segment.start)
                    end_ms = _to_ms(segment.end)
                    metadata: dict[str, object] = {}
                    if detected_language:
                        metadata["language"] = detected_language
                    avg_logprob = getattr(segment, "avg_logprob", None)
                    if avg_logprob is not None:
                        metadata["avg_logprob"] = float(avg_logprob)
                        metadata["confidence"] = round(_confidence(avg_logprob), 4)
                    no_speech = getattr(segment, "no_speech_prob", None)
                    if no_speech is not None:
                        metadata["no_speech_prob"] = float(no_speech)
                    pages.append(
                        ParsedPage(
                            page_number=None,
                            text=text,
                            start_ms=start_ms,
                            end_ms=end_ms,
                            metadata=metadata,
                        )
                    )
            except TranscriptionError:
                raise
            except Exception as exc:  # noqa: BLE001 - normalize engine errors
                raise TranscriptionError("Audio transcription failed.") from exc
            if not pages:
                raise TranscriptionError("No speech was detected in the audio.")
            return pages
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)


def _to_ms(seconds: float) -> int:
    return max(0, int(round(float(seconds) * 1000)))


def _confidence(avg_logprob: float) -> float:
    """Map an average log-probability to a bounded [0, 1] confidence estimate."""
    try:
        value = math.exp(float(avg_logprob))
    except (OverflowError, ValueError):
        return 0.0
    return min(1.0, max(0.0, value))


__all__ = ["LocalWhisperTranscriptionProvider", "TranscriptionError"]
