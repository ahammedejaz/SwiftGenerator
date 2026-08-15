import pytest
from pydantic import ValidationError

from app.agents.providers.openrouter import OpenRouterClient
from app.config import Settings


def settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "ai_provider": "openrouter",
        "app_env": "development",
        "database_url": "postgresql+psycopg://user:pass@localhost/swift_platform",
        "auth_mode": "oidc",
        "session_secure_cookies": True,
        "mock_uat_connector_enabled": False,
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def test_openrouter_safe_defaults_are_pinned() -> None:
    value = settings()
    assert value.ai_provider == "openrouter"
    assert value.ai_mode == "required"
    assert value.openrouter_primary_model == "openai/gpt-5.4-mini"
    assert value.openrouter_escalation_model == "openai/gpt-5.4"
    assert value.openrouter_require_parameters is True
    assert value.openrouter_data_collection == "deny"
    assert value.openrouter_zdr_required is True
    assert value.openrouter_log_content is False


def test_key_absence_is_controlled_and_secret_repr_is_masked() -> None:
    unconfigured = OpenRouterClient(settings())
    assert unconfigured.configured is False
    with pytest.raises(Exception, match="not configured"):
        unconfigured.build_headers()

    configured_settings = settings(openrouter_api_key="test-secret-key")
    assert "test-secret-key" not in repr(configured_settings)
    headers = OpenRouterClient(configured_settings).build_headers()
    assert headers["Authorization"] == "Bearer test-secret-key"
    assert "test-secret-key" not in repr(headers.keys())


@pytest.mark.parametrize(
    "slug",
    ["openrouter/auto", "openrouter/free", "openai/gpt-latest", "model-without-provider"],
)
def test_floating_or_router_model_slugs_are_rejected(slug: str) -> None:
    with pytest.raises(ValidationError):
        settings(openrouter_primary_model=slug)


def test_mock_provider_is_test_only() -> None:
    with pytest.raises(ValidationError):
        settings(ai_provider="mock", app_env="production")
    assert settings(ai_provider="mock", app_env="test").ai_provider == "mock"


def test_production_cannot_disable_privacy_controls() -> None:
    with pytest.raises(ValidationError):
        settings(app_env="production", openrouter_zdr_required=False)
    with pytest.raises(ValidationError):
        settings(app_env="production", openrouter_data_collection="allow")
    with pytest.raises(ValidationError):
        settings(app_env="production", openrouter_require_parameters=False)


def test_invalid_limits_and_content_logging_are_rejected() -> None:
    with pytest.raises(ValidationError):
        settings(openrouter_max_retries=10)
    with pytest.raises(ValidationError):
        settings(openrouter_confidence_threshold=1.1)
    with pytest.raises(ValidationError):
        settings(openrouter_log_content=True)


def test_optional_header_values_reject_control_characters_and_invalid_urls() -> None:
    with pytest.raises(ValidationError):
        settings(openrouter_http_referer="javascript:unsafe")
    with pytest.raises(ValidationError):
        settings(openrouter_app_title="unsafe\nheader")
    with pytest.raises(ValidationError):
        settings(openrouter_api_key="unsafe\nkey")


def test_cache_requires_server_side_hmac_secret_in_production() -> None:
    with pytest.raises(ValidationError, match="AI_CACHE_HMAC_SECRET"):
        settings(app_env="production")
    with pytest.raises(ValidationError, match="at least 32"):
        settings(ai_cache_hmac_secret="too-short")
    configured = settings(
        app_env="production",
        ai_cache_hmac_secret="synthetic-production-cache-secret-32-chars",
    )
    assert configured.ai_cache_enabled is True
    assert "synthetic-production-cache-secret" not in repr(configured)


def test_cache_can_be_explicitly_disabled_without_a_secret() -> None:
    configured = settings(app_env="production", ai_cache_enabled=False)
    assert configured.ai_cache_enabled is False
