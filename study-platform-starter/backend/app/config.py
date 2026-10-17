"""Typed application settings with environment-aware validation.

Rules:
- Development/local mode must boot even when integrations are intentionally
  unconfigured, so that ``/health`` and ``/ready`` can respond.
- Non-development environments fail fast when required variables are missing.
- Secret values are never included in error messages or logs: only variable
  names are reported as present/missing.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigError(RuntimeError):
    """Raised when required configuration is missing for the active environment."""

    def __init__(self, missing: list[str], environment: str) -> None:
        self.missing = sorted(dict.fromkeys(missing))
        self.environment = environment
        super().__init__(
            "Missing required configuration for environment "
            f"'{environment}': {', '.join(self.missing)}"
        )


def _is_local(environment: str) -> bool:
    return environment.strip().lower() in {"development", "dev", "local", "test", "testing"}


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "AI Study Platform API"
    app_version: str = "0.1.0"
    log_level: str = "INFO"
    max_upload_size_mb: int = 100

    # Comma-separated list of allowed browser origins.
    frontend_origin: str = "http://localhost:3000"

    # Database / queue
    database_url: str = ""
    redis_url: str = ""

    # Supabase Auth (JWT verification). Issuer/JWKS are derived from the URL
    # when not given explicitly.
    supabase_url: str = ""
    supabase_issuer: str = ""
    supabase_jwks_url: str = ""
    supabase_audience: str = "authenticated"

    # Cloudflare R2 (private object storage)
    cloudflare_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "study-platform-files"
    r2_endpoint_url: str = ""

    # Object storage selection and lifecycle
    storage_backend: str = "auto"  # "auto" | "r2" | "local"
    local_storage_dir: str = ".data/storage"
    api_public_base_url: str = "http://localhost:8000"
    signed_url_ttl_seconds: int = 300
    upload_rate_limit_per_minute: int = 30
    duplicate_similarity_threshold: float = 0.8

    # Chat generation. Any OpenAI-compatible provider works (OpenRouter, Google
    # Gemini, Groq, ...). Prefer these AI_* names over vendor-specific ones.
    ai_provider: str = ""  # informational label only (e.g. "gemini", "groq")
    ai_api_key: str = ""
    ai_base_url: str = "https://openrouter.ai/api/v1"
    ai_chat_model: str = ""
    ai_site_url: str = ""
    ai_app_name: str = ""

    # Embeddings are configured independently from the chat model.
    embedding_provider: str = ""
    embedding_model: str = ""
    embedding_api_key: str = ""
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_dimensions: int | None = None

    # AI request behavior and RAG budgeting.
    ai_request_timeout_seconds: float = 60.0
    ai_max_retries: int = 3
    rag_top_k: int = 6
    rag_max_context_chars: int = 12000
    rag_max_output_tokens: int = 900
    chunk_target_chars: int = 800
    chunk_overlap_chars: int = 150

    # Audio transcription (optional; the provider is disabled until configured).
    transcription_provider: str = ""  # "" | "none" | "local" (local faster-whisper)
    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_default_language: str = ""  # "" = auto-detect

    # Study artifact generation.
    artifact_max_output_tokens: int = 2000
    artifact_max_source_chars: int = 16000

    internal_api_secret: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        level = value.strip().upper()
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
        if level not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}")
        return level

    @field_validator("max_upload_size_mb")
    @classmethod
    def _validate_upload_size(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("max_upload_size_mb must be a positive integer")
        return value

    @field_validator("storage_backend")
    @classmethod
    def _validate_storage_backend(cls, value: str) -> str:
        backend = value.strip().lower()
        allowed = {"auto", "r2", "local"}
        if backend not in allowed:
            raise ValueError(f"storage_backend must be one of {sorted(allowed)}")
        return backend

    @field_validator("signed_url_ttl_seconds", "upload_rate_limit_per_minute")
    @classmethod
    def _validate_positive_int(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("value must be a positive integer")
        return value

    @field_validator("duplicate_similarity_threshold")
    @classmethod
    def _validate_threshold(cls, value: float) -> float:
        if not 0.0 < value <= 1.0:
            raise ValueError("duplicate_similarity_threshold must be in (0, 1]")
        return value

    @field_validator(
        "ai_max_retries",
        "rag_top_k",
        "rag_max_context_chars",
        "rag_max_output_tokens",
        "chunk_target_chars",
        "chunk_overlap_chars",
        "artifact_max_output_tokens",
        "artifact_max_source_chars",
    )
    @classmethod
    def _validate_ai_positive_int(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("value must be a positive integer")
        return value

    @field_validator("transcription_provider")
    @classmethod
    def _validate_transcription_provider(cls, value: str) -> str:
        provider = value.strip().lower()
        if provider not in {"", "none", "local"}:
            raise ValueError("transcription_provider must be one of ['', 'none', 'local']")
        return provider

    @field_validator("ai_request_timeout_seconds")
    @classmethod
    def _validate_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("ai_request_timeout_seconds must be positive")
        return value

    @field_validator("embedding_dimensions")
    @classmethod
    def _validate_embedding_dimensions(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("embedding_dimensions must be a positive integer")
        return value

    @property
    def r2_configured(self) -> bool:
        return all(
            _has_value(getattr(self, name))
            for name in (
                "r2_access_key_id",
                "r2_secret_access_key",
                "r2_bucket_name",
                "r2_endpoint_url",
            )
        )

    @property
    def supabase_issuer_url(self) -> str:
        """Issuer URL, derived from ``supabase_url`` when not set explicitly."""
        if self.supabase_issuer.strip():
            return self.supabase_issuer.strip()
        if self.supabase_url.strip():
            return f"{self.supabase_url.strip().rstrip('/')}/auth/v1"
        return ""

    @property
    def supabase_jwks_url_resolved(self) -> str:
        """JWKS URL, derived from the issuer when not set explicitly."""
        if self.supabase_jwks_url.strip():
            return self.supabase_jwks_url.strip()
        issuer = self.supabase_issuer_url
        return f"{issuer}/.well-known/jwks.json" if issuer else ""

    @property
    def supabase_identity_configured(self) -> bool:
        return _has_value(self.supabase_issuer_url) and _has_value(self.supabase_jwks_url_resolved)

    @property
    def is_local(self) -> bool:
        return _is_local(self.app_env)

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origin.split(",") if origin.strip()]

    def required_for_environment(self) -> list[str]:
        """Return the names of variables required for the active environment."""
        if self.is_local:
            return []
        missing: list[str] = []
        for name in (
            "database_url",
            "ai_api_key",
            "ai_chat_model",
            "embedding_model",
            "embedding_api_key",
        ):
            if not _has_value(getattr(self, name)):
                missing.append(name)
        if not self.supabase_identity_configured:
            missing.append("supabase_url")
        if self.storage_backend != "local":
            for name in (
                "r2_access_key_id",
                "r2_secret_access_key",
                "r2_bucket_name",
                "r2_endpoint_url",
            ):
                if not _has_value(getattr(self, name)):
                    missing.append(name)
        return missing

    def missing_required(self) -> list[str]:
        return self.required_for_environment()


def _has_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def validate_settings(settings: Settings) -> Settings:
    """Validate that required variables are present, raising ConfigError otherwise."""
    missing = settings.missing_required()
    if missing:
        raise ConfigError(missing, settings.app_env)
    return settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


__all__ = [
    "ConfigError",
    "Settings",
    "get_settings",
    "settings",
    "validate_settings",
]
