"""Upload validation: size, declared vs detected content type, and a malware hook.

Content type is determined from magic bytes on the server. A browser-supplied
``Content-Type`` is advisory only and never trusted to allow a file through.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

MAX_FILENAME_LENGTH = 255

# Allow-list of detected MIME types. Keep intentionally narrow.
ALLOWED_MIME_TYPES: frozenset[str] = frozenset(
    {
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "audio/mpeg",
        "audio/wav",
        "audio/ogg",
        "audio/mp4",
        "video/mp4",
        "text/plain",
        "text/markdown",
        "application/zip",
    }
)

MATERIAL_TYPE_BY_MIME: dict[str, str] = {
    "application/pdf": "document",
    "application/zip": "document",
    "text/plain": "document",
    "text/markdown": "document",
    "image/png": "image",
    "image/jpeg": "image",
    "image/gif": "image",
    "image/webp": "image",
    "audio/mpeg": "audio",
    "audio/wav": "audio",
    "audio/ogg": "audio",
    "audio/mp4": "audio",
    "video/mp4": "video",
}


class UploadValidationError(ValueError):
    """Raised when an upload fails validation; maps to HTTP 422."""


class FileTooLarge(UploadValidationError):
    pass


@dataclass(frozen=True)
class ScanResult:
    clean: bool
    reason: str | None = None


class MalwareScanner(Protocol):
    def scan(self, data: bytes, filename: str) -> ScanResult: ...


class NullMalwareScanner:
    """No-op scanner used until a real AV/content scanner is wired in."""

    def scan(self, data: bytes, filename: str) -> ScanResult:  # noqa: ARG002
        return ScanResult(clean=True)


def get_malware_scanner() -> MalwareScanner:
    """Injection point for a real scanner (e.g. ClamAV) in later phases."""
    return NullMalwareScanner()


def detect_mime(data: bytes) -> str | None:
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "audio/wav"
    if data.startswith(b"OggS"):
        return "audio/ogg"
    if data.startswith(b"ID3") or data[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio/mpeg"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in (b"M4A ", b"mp42", b"isom", b"iso2"):
            return "audio/mp4"
        if brand in (b"isom", b"mp42", b"avc1", b"iso5", b"dash"):
            return "video/mp4"
        return "video/mp4"
    if data.startswith(b"PK\x03\x04"):
        return "application/zip"
    if _looks_like_text(data):
        return "text/plain"
    return None


def _looks_like_text(data: bytes) -> bool:
    if not data:
        return False
    sample = data[:4096]
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def validate_upload(
    data: bytes,
    *,
    filename: str,
    declared_content_type: str | None,
    max_bytes: int,
) -> tuple[str, str]:
    """Validate bytes and return ``(detected_mime, material_type)``.

    Raises ``UploadValidationError`` (or ``FileTooLarge``) on failure.
    """
    if not filename or len(filename) > MAX_FILENAME_LENGTH:
        raise UploadValidationError("Invalid filename.")
    if not data:
        raise UploadValidationError("Empty file.")
    if len(data) > max_bytes:
        raise FileTooLarge(f"File exceeds the {max_bytes} byte limit.")

    detected = detect_mime(data)
    if detected is None:
        raise UploadValidationError("Unsupported or unrecognized file type.")
    if detected not in ALLOWED_MIME_TYPES:
        raise UploadValidationError(f"File type '{detected}' is not allowed.")

    declared = (declared_content_type or "").split(";")[0].strip().lower()
    # A declared type that clearly disagrees with the detected binary is rejected.
    if declared and declared != detected and not _compatible(declared, detected):
        raise UploadValidationError("Declared content type does not match file content.")

    return detected, MATERIAL_TYPE_BY_MIME.get(detected, "other")


def _compatible(declared: str, detected: str) -> bool:
    if declared == "application/octet-stream":
        return True
    if declared.startswith("text/") and detected.startswith("text/"):
        return True
    return False


__all__ = [
    "ALLOWED_MIME_TYPES",
    "FileTooLarge",
    "MalwareScanner",
    "MATERIAL_TYPE_BY_MIME",
    "NullMalwareScanner",
    "ScanResult",
    "UploadValidationError",
    "detect_mime",
    "get_malware_scanner",
    "validate_upload",
]
