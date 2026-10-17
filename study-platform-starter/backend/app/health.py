"""Health and readiness contracts.

``/health`` is a liveness probe: it answers as long as the process is running.
``/ready`` reports integration status ONLY. It never returns secret values,
connection strings, endpoints, or credential material.
"""

from __future__ import annotations

from typing import Any

from app.config import Settings


def _has(value: str) -> bool:
    return bool(value and value.strip())


def integration_status(settings: Settings) -> dict[str, Any]:
    """Report whether each integration is configured, without verifying it.

    Connectivity verification is added in later phases (database, storage, AI).
    Until then we explicitly report ``configured`` rather than ``ok`` to avoid
    claiming a connection that has not been tested.
    """
    database_configured = _has(settings.database_url)
    storage_configured = all(
        _has(getattr(settings, name))
        for name in ("r2_access_key_id", "r2_secret_access_key", "r2_endpoint_url", "r2_bucket_name")
    )
    identity_configured = settings.supabase_identity_configured
    ai_configured = _has(settings.ai_api_key) and _has(settings.ai_chat_model)
    embeddings_configured = _has(settings.embedding_provider) and _has(settings.embedding_model)
    transcription_configured = _has(settings.transcription_provider) and (
        settings.transcription_provider != "none"
    )
    queue_configured = _has(settings.redis_url)

    return {
        "database": {"configured": database_configured, "verified": False},
        "object_storage": {"configured": storage_configured, "verified": False},
        "identity": {"configured": identity_configured, "verified": False},
        "ai_chat": {"configured": ai_configured, "verified": False},
        "embeddings": {"configured": embeddings_configured, "verified": False},
        "transcription": {"configured": transcription_configured, "verified": False},
        "queue": {"configured": queue_configured, "verified": False},
    }


def health_payload(settings: Settings) -> dict[str, Any]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_env,
    }


def readiness_payload(settings: Settings) -> dict[str, Any]:
    checks = integration_status(settings)
    return {
        "status": "ready",
        "environment": settings.app_env,
        "checks": checks,
    }


__all__ = ["health_payload", "integration_status", "readiness_payload"]
