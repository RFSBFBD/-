"""Provider-agnostic private object storage contract.

Concrete providers keep bytes private and issue short-lived signed download
URLs. Secrets never leave the backend.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class StorageError(RuntimeError):
    """Raised for unrecoverable storage failures."""


class ObjectNotFound(StorageError):
    pass


class ObjectTooLarge(StorageError):
    pass


@dataclass(frozen=True)
class SignedUrl:
    url: str
    expires_in: int
    method: str


@dataclass(frozen=True)
class ObjectInfo:
    key: str
    size_bytes: int
    content_type: str | None


@runtime_checkable
class StorageProvider(Protocol):
    name: str

    def put_object(self, key: str, data: bytes, content_type: str | None = None) -> None: ...

    def get_object(self, key: str, max_bytes: int) -> bytes: ...

    def head_object(self, key: str) -> ObjectInfo | None: ...

    def delete_object(self, key: str) -> None: ...

    def create_download_url(self, key: str, *, expires_in: int) -> SignedUrl: ...


__all__ = [
    "ObjectInfo",
    "ObjectNotFound",
    "ObjectTooLarge",
    "SignedUrl",
    "StorageError",
    "StorageProvider",
]
