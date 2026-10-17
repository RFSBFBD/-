import pytest

from app.config import ConfigError, Settings, validate_settings


def make_settings(**overrides) -> Settings:
    base = dict(_env_file=None)
    base.update(overrides)
    return Settings(**base)


def test_development_allows_unconfigured_integrations():
    settings = make_settings(app_env="development")
    assert settings.is_local is True
    assert validate_settings(settings) is settings


def test_production_requires_core_variables():
    settings = make_settings(app_env="production")
    with pytest.raises(ConfigError) as excinfo:
        validate_settings(settings)
    assert "database_url" in excinfo.value.missing
    assert "supabase_url" in excinfo.value.missing
    assert "ai_chat_model" in excinfo.value.missing


def test_production_passes_when_required_present():
    settings = make_settings(
        app_env="production",
        database_url="postgresql://example/db",
        supabase_url="https://supabase.example.com",
        supabase_issuer="https://supabase.example.com",
        ai_api_key="key",
        ai_chat_model="some/model",
        embedding_model="embed/model",
        embedding_api_key="embedkey",
        r2_access_key_id="r2key",
        r2_secret_access_key="r2secret",
        r2_bucket_name="bucket",
        r2_endpoint_url="https://account.r2.cloudflarestorage.com",
    )
    assert validate_settings(settings) is settings


def test_production_requires_r2_unless_local_storage():
    settings = make_settings(
        app_env="production",
        database_url="postgresql://example/db",
        supabase_url="https://supabase.example.com",
        supabase_issuer="https://supabase.example.com",
        ai_api_key="key",
        ai_chat_model="some/model",
    )
    with pytest.raises(ConfigError) as excinfo:
        validate_settings(settings)
    assert "r2_access_key_id" in excinfo.value.missing
    assert "r2_endpoint_url" in excinfo.value.missing

    local_settings = make_settings(
        app_env="production",
        storage_backend="local",
        database_url="postgresql://example/db",
        supabase_url="https://supabase.example.com",
        supabase_issuer="https://supabase.example.com",
        ai_api_key="key",
        ai_chat_model="some/model",
        embedding_model="embed/model",
        embedding_api_key="embedkey",
    )
    assert validate_settings(local_settings) is local_settings


def test_config_error_never_leaks_values():
    settings = make_settings(
        app_env="production",
        database_url="postgresql://user:supersecret@host/db",
    )
    with pytest.raises(ConfigError) as excinfo:
        validate_settings(settings)
    message = str(excinfo.value)
    assert "supersecret" not in message
    assert "postgresql://" not in message


def test_cors_origins_are_split_and_trimmed():
    settings = make_settings(frontend_origin="http://a.test, http://b.test ,")
    assert settings.cors_origins == ["http://a.test", "http://b.test"]


def test_invalid_log_level_is_rejected():
    with pytest.raises(ValueError):
        make_settings(log_level="LOUD")


def test_invalid_upload_size_is_rejected():
    with pytest.raises(ValueError):
        make_settings(max_upload_size_mb=0)


def test_invalid_storage_backend_is_rejected():
    with pytest.raises(ValueError):
        make_settings(storage_backend="s3")


def test_invalid_similarity_threshold_is_rejected():
    with pytest.raises(ValueError):
        make_settings(duplicate_similarity_threshold=0)


def test_blank_optional_env_values_fall_back_to_defaults(monkeypatch):
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "")
    monkeypatch.setenv("AI_MAX_RETRIES", "")
    monkeypatch.setenv("DATABASE_URL", "")
    settings = Settings(_env_file=None)
    assert settings.embedding_dimensions is None
    assert settings.ai_max_retries == 3
    assert settings.database_url == ""
