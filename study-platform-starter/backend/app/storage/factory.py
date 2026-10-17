"""Storage provider factory and FastAPI dependency."""

from __future__ import annotations

from functools import lru_cache

from app.config import settings
from app.storage.base import StorageProvider
from app.storage.local import LocalStorageProvider


@lru_cache(maxsize=1)
def get_storage_provider() -> StorageProvider:
    """Return the configured provider.

    ``auto`` prefers R2 when credentials are present and falls back to local
    storage otherwise (development/test).
    """
    use_r2 = settings.storage_backend == "r2" or (
        settings.storage_backend == "auto" and settings.r2_configured
    )
    if use_r2:
        from app.storage.r2 import R2StorageProvider

        return R2StorageProvider(
            access_key_id=settings.r2_access_key_id,
            secret_access_key=settings.r2_secret_access_key,
            bucket=settings.r2_bucket_name,
            endpoint_url=settings.r2_endpoint_url,
        )
    return LocalStorageProvider(
        base_dir=settings.local_storage_dir,
        public_base_url=settings.api_public_base_url,
        signing_secret=settings.internal_api_secret,
    )


def get_storage() -> StorageProvider:
    """FastAPI dependency wrapper (overridable in tests)."""
    return get_storage_provider()


__all__ = ["get_storage", "get_storage_provider"]
