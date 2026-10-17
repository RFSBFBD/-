"""Local filesystem storage provider for development and tests.

Download URLs are backend-proxied and protected by an HMAC signature plus a
short expiry. Paths are normalized to prevent traversal outside the base dir.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import tempfile
from pathlib import Path
from urllib.parse import quote

from app.clock import utcnow
from app.storage.base import ObjectInfo, ObjectNotFound, ObjectTooLarge, SignedUrl

_LOCAL_DEV_SECRET = "local-dev-storage-secret"


class LocalStorageProvider:
    name = "local"

    def __init__(self, base_dir: str, public_base_url: str, signing_secret: str = "") -> None:
        self._base_dir = Path(base_dir).resolve()
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._public_base_url = public_base_url.rstrip("/")
        self._secret = (signing_secret or _LOCAL_DEV_SECRET).encode("utf-8")

    def _path(self, key: str) -> Path:
        normalized = key.replace("\\", "/").lstrip("/")
        parts = [part for part in normalized.split("/") if part and part != "."]
        if not parts or ".." in parts:
            raise ObjectNotFound("Invalid storage key.")
        target = (self._base_dir / Path(*parts)).resolve()
        if self._base_dir not in target.parents and target != self._base_dir:
            raise ObjectNotFound("Invalid storage key.")
        return target

    def put_object(self, key: str, data: bytes, content_type: str | None = None) -> None:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(dir=str(target.parent))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(temp_name, target)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def get_object(self, key: str, max_bytes: int) -> bytes:
        target = self._path(key)
        if not target.is_file():
            raise ObjectNotFound(f"Object not found: {key}")
        if target.stat().st_size > max_bytes:
            raise ObjectTooLarge(f"Object exceeds {max_bytes} bytes.")
        with target.open("rb") as handle:
            return handle.read(max_bytes + 1)

    def head_object(self, key: str) -> ObjectInfo | None:
        target = self._path(key)
        if not target.is_file():
            return None
        return ObjectInfo(key=key, size_bytes=target.stat().st_size, content_type=None)

    def delete_object(self, key: str) -> None:
        target = self._path(key)
        if target.is_file():
            target.unlink()

    def create_download_url(self, key: str, *, expires_in: int) -> SignedUrl:
        expires = int(utcnow().timestamp()) + int(expires_in)
        signature = sign_local_key(self._secret, key, expires)
        url = (
            f"{self._public_base_url}/storage/local/{quote(key, safe='/')}"
            f"?expires={expires}&sig={signature}"
        )
        return SignedUrl(url=url, expires_in=int(expires_in), method="GET")

    def verify_download(self, key: str, expires: int, signature: str) -> bool:
        return verify_local_signature(self._secret, key, expires, signature)

    def path_for(self, key: str) -> Path:
        target = self._path(key)
        if not target.is_file():
            raise ObjectNotFound(f"Object not found: {key}")
        return target


def sign_local_key(secret: bytes, key: str, expires: int) -> str:
    message = f"{key}\n{expires}".encode("utf-8")
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def verify_local_signature(secret: bytes, key: str, expires: int, signature: str) -> bool:
    if expires < int(utcnow().timestamp()):
        return False
    expected = sign_local_key(secret, key, expires)
    return hmac.compare_digest(expected, signature)


__all__ = ["LocalStorageProvider", "sign_local_key", "verify_local_signature"]
