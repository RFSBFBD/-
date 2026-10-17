"""Document parsing for ingestion: PDF and plain-text, with an OCR hook.

Parsing failures raise ``DocumentParseError``; ingestion records a safe failed
status rather than crashing the request.
"""

from __future__ import annotations

import io

from app.ai.base import ParsedDocument, ParsedPage

TEXT_MIME_TYPES = {"text/plain", "text/markdown"}


class DocumentParseError(Exception):
    """Raised for unparseable or unsupported documents."""


class OcrUnavailable(DocumentParseError):
    """Scanned/empty PDF that requires OCR, which is not configured."""


class DocumentParser:
    """Default parser: PDF text extraction (pypdf) and UTF-8 text."""

    name = "default"

    def parse(self, data: bytes, *, mime_type: str, filename: str) -> ParsedDocument:
        if mime_type == "application/pdf":
            return self._parse_pdf(data)
        if mime_type in TEXT_MIME_TYPES or mime_type.startswith("text/"):
            return self._parse_text(data)
        raise DocumentParseError(f"Unsupported document type '{mime_type}'.")

    def _parse_text(self, data: bytes) -> ParsedDocument:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DocumentParseError("Text document is not valid UTF-8.") from exc
        if not text.strip():
            raise DocumentParseError("Document contains no extractable text.")
        return ParsedDocument(pages=[ParsedPage(page_number=1, text=text)], parser=self.name)

    def _parse_pdf(self, data: bytes) -> ParsedDocument:
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover - dependency present in prod
            raise DocumentParseError("PDF parsing support is not installed.") from exc

        try:
            reader = PdfReader(io.BytesIO(data))
            pages: list[ParsedPage] = []
            for index, page in enumerate(reader.pages, start=1):
                text = (page.extract_text() or "").strip()
                if text:
                    pages.append(ParsedPage(page_number=index, text=text))
        except Exception as exc:  # noqa: BLE001 - normalize library errors
            raise DocumentParseError("Failed to parse PDF.") from exc

        if not pages:
            raise OcrUnavailable("PDF has no extractable text; OCR is required but not configured.")
        return ParsedDocument(pages=pages, parser=self.name)


def get_document_parser() -> DocumentParser:
    return DocumentParser()


__all__ = [
    "DocumentParseError",
    "DocumentParser",
    "OcrUnavailable",
    "get_document_parser",
]
