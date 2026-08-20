from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
#: Where the committed configuration lives; every source path below defaults into it.
#: `backend/config`, not `PROJECT_ROOT/config` — PROJECT_ROOT is the repository root.
CONFIG_ROOT = Path(__file__).resolve().parents[1] / "config"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    app_env: str = "development"
    app_name: str = "Intelligent SWIFT Message Engineering Platform"
    database_url: str = "sqlite:///./data/securities_studio.db"
    report_directory: str = "./data/reports"
    # Both spellings of the same machine: a tester opening 127.0.0.1:3000 and one opening
    # localhost:3000 send different Origin headers, and being refused by CORS for choosing
    # the other one is unexplainable from the browser. Comma-separated; the first is the
    # canonical one.
    frontend_origin: str = "http://localhost:3000,http://127.0.0.1:3000"
    max_upload_bytes: int = 5_242_880
    max_request_bytes: int = 6_291_456
    max_bulk_rows: int = 1_000
    rate_limit_requests_per_minute: int = 600
    ai_rate_limit_requests_per_minute: int = 30
    ai_provider: str = "openrouter"
    ai_mode: str = "required"
    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_primary_model: str = "openai/gpt-5.4-mini"
    openrouter_escalation_model: str = "openai/gpt-5.4"
    openrouter_escalation_enabled: bool = True
    openrouter_http_referer: str = ""
    openrouter_app_title: str = "Intelligent SWIFT Message Engineering Platform"
    openrouter_require_parameters: bool = True
    openrouter_allow_provider_fallbacks: bool = True
    openrouter_data_collection: str = "deny"
    openrouter_zdr_required: bool = True
    openrouter_timeout_seconds: float = 30.0
    openrouter_connect_timeout_seconds: float = 5.0
    openrouter_operation_timeout_seconds: float = 45.0
    openrouter_max_retries: int = 2
    openrouter_max_input_chars: int = 6_000
    openrouter_max_output_tokens: int = 1_200
    openrouter_confidence_threshold: float = 0.80
    openrouter_daily_request_budget: int | None = None
    openrouter_daily_token_budget: int | None = None
    openrouter_log_content: bool = False
    openrouter_retry_base_seconds: float = 0.25
    openrouter_retry_max_seconds: float = 3.0
    openrouter_circuit_failure_threshold: int = 5
    openrouter_circuit_cooldown_seconds: float = 30.0
    ai_cache_enabled: bool = True
    ai_cache_hmac_secret: SecretStr | None = None
    ai_cache_key_version: str = "v1"
    ai_cache_intent_ttl_seconds: int = 2_592_000
    ai_cache_explanation_ttl_seconds: int = 7_776_000
    ai_cache_validation_ttl_seconds: int = 2_592_000
    ai_cache_l1_max_entries: int = 256
    ai_cache_stampede_wait_seconds: float = 45.0
    ai_cache_knowledge_version: str = "KB_2026_08_05_V2"
    ai_cache_taxonomy_version: str = "WORKFLOW_TAXONOMY_V1"
    ai_cache_admin_enabled: bool = False
    demo_reset_enabled: bool = True
    demo_reset_key: str = ""
    real_data_mode_enabled: bool = False
    auth_mode: str = "development"
    session_cookie_name: str = "swift_platform_session"
    session_ttl_seconds: int = 28_800
    session_secure_cookies: bool = False
    session_hmac_secret: SecretStr | None = None
    csrf_cookie_name: str = "swift_platform_csrf"
    csrf_header_name: str = "X-CSRF-Token"
    data_encryption_key: SecretStr | None = None
    data_encryption_key_id: str = "local-v1"
    data_retention_days: int = 90
    submission_mode: str = "disabled"
    production_submission_enabled: bool = False
    mock_uat_connector_enabled: bool = False
    external_validation_required_for_submission: bool = True
    fin_export_enabled: bool = True
    rje_export_enabled: bool = False
    # Comma-separated service keys for the automation API. Empty leaves /api/v1 open in
    # development and closed everywhere else. Never commit a value here.
    automation_api_keys: SecretStr | None = None
    max_excel_scenarios: int = 200

    # Where authorised specification artifacts are read from. Each defaults to the
    # directory committed here, so a clean clone behaves exactly as before; pointing one at
    # a licensed drop keeps the import a configuration change rather than a code change.
    # See docs/authoritative-sources.md.
    mt_specification_manifest: str = ""
    mx_specification_directory: str = ""
    mx_official_xsd_directory: str = ""
    client_profile_directory: str = ""
    #: Reviewed, source-controlled rule packs. Only fully reviewed packs load from here.
    rule_pack_directory: str = ""
    #: Where business-rule source documents are dropped. Licensed material stays here and
    #: is never committed; only synthetic fixtures live in the repository copy.
    rule_source_directory: str = ""
    #: Candidate rules produced by extraction. Never loaded at runtime, never committed.
    rule_candidate_directory: str = "./data/rule_candidates"
    #: Where an operator drops SWIFT MyStandards Message Reference Guides. Licensed
    #: documents: read locally, never committed, never sent anywhere. Empty means the
    #: ignored directory beside the checkout that docs/mt-real-semantic-phase-05b.md names.
    mt_mrg_source_directory: str = ""

    # Rule extraction (offline developer tooling; no runtime path calls a model).
    rule_extractor_model: str = ""
    rule_secondary_extractor_model: str = ""
    rule_refuter_model: str = ""
    rule_extraction_cache_enabled: bool = True
    rule_extraction_cache_directory: str = "./data/rule_extraction_cache"
    rule_extraction_max_fields: int = 400
    #: The synthetic corpus the extraction evaluation runs against.
    rule_evaluation_directory: str = ""

    # -- Phase 6: organisation-approved AI endpoint (Azure OpenAI or any OpenAI-compatible
    # -- server). The canonical names come first; the second spelling of each alias is the
    # -- one the operator's existing .env already uses, honoured so nothing has to be renamed.
    # -- Only the origin of AI_ENDPOINT is used; its path and query are ignored except that an
    # -- api-version query is kept for the legacy deployment-scoped Azure surface.
    ai_endpoint: str = Field(
        "", validation_alias=AliasChoices("AI_ENDPOINT", "ENDPOINT")
    )
    ai_api_key: SecretStr | None = Field(
        None, validation_alias=AliasChoices("AI_API_KEY", "API_KEY")
    )
    ai_chat_deployment: str = Field(
        "", validation_alias=AliasChoices("AI_CHAT_DEPLOYMENT", "MODEL")
    )
    ai_api_version: str = Field("", validation_alias=AliasChoices("AI_API_VERSION"))
    ai_max_output_tokens: int = 2_000
    embeddings_deployment: str = Field(
        "", validation_alias=AliasChoices("EMBEDDINGS_DEPLOYMENT", "EMBEDDINGS_DEPLOYMENT")
    )
    #: azure_openai | openai_compatible | fake | disabled | auto. ``auto`` (the default)
    #: becomes azure_openai when the endpoint host ends in openai.azure.com, openai_compatible
    #: when an endpoint and key exist, and disabled otherwise.
    embedding_provider: str = "auto"
    #: Sent as ``dimensions`` when set; every stored vector is validated against it on read.
    embedding_dimensions: int | None = None
    embedding_batch_size: int = 64
    embedding_timeout_seconds: float = 30.0
    embedding_max_retries: int = 3

    # -- Phase 6: local knowledge base. Disabled unless asked for, so a production-style
    # -- process never loads arbitrary workstation files.
    #: disabled | local | local_uat. local_uat additionally enables the sync endpoint.
    knowledge_mode: str = "disabled"
    #: Comma-separated roots that `make knowledge-sync` walks. Relative to the project root.
    knowledge_source_dir: str = "swiftKnowledgeBase"
    knowledge_db_path: str = "build/knowledge/knowledge.sqlite3"
    knowledge_pack_dir: str = "build/knowledge/packs"
    knowledge_source_cache_dir: str = "build/knowledge/source-cache"
    knowledge_auto_sync_on_start: bool = False
    #: Licensed material leaves the machine only when the operator says so, twice: the
    #: global gate and the per-classification list. An API key is never permission.
    knowledge_external_embedding_allowed: bool = False
    knowledge_external_llm_allowed: bool = False
    knowledge_external_processing_classifications: str = "SYNTHETIC_FIXTURE"
    knowledge_max_source_bytes: int = 64 * 1024 * 1024
    knowledge_max_zip_member_bytes: int = 64 * 1024 * 1024
    knowledge_max_zip_total_bytes: int = 256 * 1024 * 1024
    knowledge_context_chars: int = 6_000
    knowledge_ai_max_batch: int = 20
    knowledge_ai_max_repair_attempts: int = 3
    knowledge_ai_reviewer_mode: bool = False
    #: auto | scripted | disabled. ``scripted`` returns each operation's deterministic seed
    #: and is honoured in development and test only.
    knowledge_ai_provider: str = "auto"

    @field_validator("knowledge_ai_provider")
    @classmethod
    def validate_knowledge_ai_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"auto", "scripted", "disabled"}:
            raise ValueError("KNOWLEDGE_AI_PROVIDER must be auto, scripted, or disabled")
        return normalized

    @field_validator("embedding_provider")
    @classmethod
    def validate_embedding_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"auto", "azure_openai", "openai_compatible", "fake", "disabled"}:
            raise ValueError(
                "EMBEDDING_PROVIDER must be auto, azure_openai, openai_compatible, fake, "
                "or disabled"
            )
        return normalized

    @field_validator("knowledge_mode")
    @classmethod
    def validate_knowledge_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"disabled", "local", "local_uat"}:
            raise ValueError("KNOWLEDGE_MODE must be disabled, local, or local_uat")
        return normalized

    @field_validator("ai_endpoint")
    @classmethod
    def validate_ai_endpoint(cls, value: str) -> str:
        normalized = value.strip()
        if normalized and not normalized.startswith("https://"):
            raise ValueError("AI_ENDPOINT must use HTTPS")
        return normalized

    @field_validator("ai_api_key")
    @classmethod
    def validate_ai_api_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        if any(ord(character) < 32 for character in value.get_secret_value()):
            raise ValueError("AI_API_KEY contains invalid control characters")
        return value

    # -- derived, never persisted -------------------------------------------------------

    @property
    def ai_endpoint_origin(self) -> str:
        """``https://resource.openai.azure.com`` — the only part of the endpoint used."""
        if not self.ai_endpoint:
            return ""
        parsed = urlparse(self.ai_endpoint)
        return f"{parsed.scheme}://{parsed.netloc}"

    @property
    def ai_endpoint_is_azure(self) -> bool:
        host = urlparse(self.ai_endpoint).netloc.lower() if self.ai_endpoint else ""
        return host.endswith((".openai.azure.com", ".services.ai.azure.com"))

    @property
    def ai_api_version_effective(self) -> str:
        """The api-version for the legacy Azure surface: explicit setting, else the query
        string of the configured endpoint, else the current GA value."""
        if self.ai_api_version.strip():
            return self.ai_api_version.strip()
        if self.ai_endpoint:
            from_query = parse_qs(urlparse(self.ai_endpoint).query).get("api-version")
            if from_query:
                return from_query[0]
        return "2024-10-21"

    @property
    def embedding_provider_effective(self) -> str:
        if self.embedding_provider != "auto":
            return self.embedding_provider
        if not (self.ai_endpoint and self.ai_api_key and self.embeddings_deployment):
            return "disabled"
        return "azure_openai" if self.ai_endpoint_is_azure else "openai_compatible"

    @property
    def structured_ai_provider_effective(self) -> str:
        """Which structured-completion provider serves the Phase 6 AI authoring paths.

        ``ai_provider`` keeps its historical meaning for the settlement-intent screen. The
        authoring paths prefer the organisation endpoint when it is configured, fall back
        to OpenRouter when that is what exists, and are otherwise disabled.
        """
        if self.ai_provider == "disabled":
            return "disabled"
        if self.ai_provider == "mock":
            return "mock"
        if self.ai_endpoint and self.ai_api_key and self.ai_chat_deployment:
            return "azure_openai" if self.ai_endpoint_is_azure else "openai_compatible"
        if self.ai_provider == "openrouter" and self.openrouter_api_key:
            return "openrouter"
        return "disabled"

    @property
    def knowledge_enabled(self) -> bool:
        return self.knowledge_mode != "disabled"

    @field_validator("automation_api_keys")
    @classmethod
    def validate_automation_keys(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        keys = [item.strip() for item in value.get_secret_value().split(",") if item.strip()]
        if any(len(key) < 24 for key in keys):
            raise ValueError("Each automation API key must contain at least 24 characters")
        if any(any(ord(character) < 32 for character in key) for key in keys):
            raise ValueError("AUTOMATION_API_KEYS contains invalid control characters")
        return value

    @field_validator("ai_provider")
    @classmethod
    def validate_ai_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        allowed = {"openrouter", "azure_openai", "openai_compatible", "disabled", "mock"}
        if normalized not in allowed:
            raise ValueError(
                "AI_PROVIDER must be openrouter, azure_openai, openai_compatible, disabled, "
                "or mock"
            )
        return normalized

    @field_validator("ai_mode")
    @classmethod
    def validate_ai_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"required", "optional"}:
            raise ValueError("AI_MODE must be required or optional")
        return normalized

    @field_validator("auth_mode")
    @classmethod
    def validate_auth_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"development", "oidc", "saml", "disabled"}:
            raise ValueError("AUTH_MODE must be development, oidc, saml, or disabled")
        return normalized

    @field_validator("submission_mode")
    @classmethod
    def validate_submission_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"disabled", "uat", "production"}:
            raise ValueError("SUBMISSION_MODE must be disabled, uat, or production")
        return normalized

    @field_validator("data_encryption_key_id")
    @classmethod
    def validate_encryption_key_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > 64 or any(ord(char) < 32 for char in normalized):
            raise ValueError("DATA_ENCRYPTION_KEY_ID is invalid")
        return normalized

    @field_validator("openrouter_base_url")
    @classmethod
    def validate_openrouter_base_url(cls, value: str) -> str:
        normalized = value.rstrip("/")
        if not normalized.startswith("https://"):
            raise ValueError("OPENROUTER_BASE_URL must use HTTPS")
        return normalized

    @field_validator("openrouter_primary_model", "openrouter_escalation_model")
    @classmethod
    def validate_pinned_model_slug(cls, value: str) -> str:
        normalized = value.strip()
        lowered = normalized.lower()
        if (
            "/" not in normalized
            or lowered in {"openrouter/auto", "openrouter/free"}
            or "latest" in lowered
            or lowered.endswith(":free")
        ):
            raise ValueError("OpenRouter models must use a pinned provider/model slug")
        return normalized

    @field_validator("openrouter_data_collection")
    @classmethod
    def validate_data_collection(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"allow", "deny"}:
            raise ValueError("OPENROUTER_DATA_COLLECTION must be allow or deny")
        return normalized

    @field_validator("openrouter_http_referer")
    @classmethod
    def validate_http_referer(cls, value: str) -> str:
        normalized = value.strip()
        if normalized and not normalized.startswith(("https://", "http://")):
            raise ValueError("OPENROUTER_HTTP_REFERER must be an HTTP(S) URL")
        if len(normalized) > 512 or any(ord(character) < 32 for character in normalized):
            raise ValueError("OPENROUTER_HTTP_REFERER contains an invalid header value")
        return normalized

    @field_validator("openrouter_app_title")
    @classmethod
    def validate_app_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > 128:
            raise ValueError("OPENROUTER_APP_TITLE must contain 1 to 128 characters")
        if any(ord(character) < 32 for character in normalized):
            raise ValueError("OPENROUTER_APP_TITLE contains an invalid header value")
        return normalized

    @field_validator("openrouter_api_key")
    @classmethod
    def validate_api_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        secret = value.get_secret_value()
        if any(ord(character) < 32 for character in secret):
            raise ValueError("OPENROUTER_API_KEY contains invalid control characters")
        return value

    @field_validator("ai_cache_hmac_secret")
    @classmethod
    def validate_cache_hmac_secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        secret = value.get_secret_value()
        if len(secret) < 32:
            raise ValueError("AI_CACHE_HMAC_SECRET must contain at least 32 characters")
        if any(ord(character) < 32 for character in secret):
            raise ValueError("AI_CACHE_HMAC_SECRET contains invalid control characters")
        return value

    @field_validator("session_hmac_secret")
    @classmethod
    def validate_session_secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        if len(value.get_secret_value()) < 32:
            raise ValueError("SESSION_HMAC_SECRET must contain at least 32 characters")
        return value

    @field_validator("data_encryption_key")
    @classmethod
    def validate_data_encryption_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        import base64

        try:
            decoded = base64.b64decode(value.get_secret_value(), validate=True)
        except ValueError as error:
            raise ValueError("DATA_ENCRYPTION_KEY must be valid base64") from error
        if len(decoded) != 32:
            raise ValueError("DATA_ENCRYPTION_KEY must decode to exactly 32 bytes")
        return value

    @model_validator(mode="after")
    def validate_ai_safety(self) -> "Settings":
        if self.ai_provider == "mock" and self.app_env != "test":
            raise ValueError("The mock AI provider is permitted only when APP_ENV=test")
        if self.knowledge_ai_provider == "scripted" and self.app_env not in {
            "development",
            "test",
        }:
            raise ValueError(
                "KNOWLEDGE_AI_PROVIDER=scripted is permitted only in development or test"
            )
        if self.app_env == "production" and (
            not self.openrouter_require_parameters
            or self.openrouter_data_collection != "deny"
            or not self.openrouter_zdr_required
        ):
            raise ValueError(
                "Production requires parameter enforcement, data-collection denial, and ZDR"
            )
        if self.openrouter_log_content:
            raise ValueError("OPENROUTER_LOG_CONTENT must remain false")
        positive_numbers = {
            "OPENROUTER_TIMEOUT_SECONDS": self.openrouter_timeout_seconds,
            "OPENROUTER_CONNECT_TIMEOUT_SECONDS": self.openrouter_connect_timeout_seconds,
            "OPENROUTER_OPERATION_TIMEOUT_SECONDS": self.openrouter_operation_timeout_seconds,
            "OPENROUTER_MAX_INPUT_CHARS": self.openrouter_max_input_chars,
            "OPENROUTER_MAX_OUTPUT_TOKENS": self.openrouter_max_output_tokens,
            "OPENROUTER_CIRCUIT_FAILURE_THRESHOLD": self.openrouter_circuit_failure_threshold,
            "OPENROUTER_CIRCUIT_COOLDOWN_SECONDS": self.openrouter_circuit_cooldown_seconds,
            "AI_RATE_LIMIT_REQUESTS_PER_MINUTE": self.ai_rate_limit_requests_per_minute,
            "AI_CACHE_INTENT_TTL_SECONDS": self.ai_cache_intent_ttl_seconds,
            "AI_CACHE_EXPLANATION_TTL_SECONDS": self.ai_cache_explanation_ttl_seconds,
            "AI_CACHE_VALIDATION_TTL_SECONDS": self.ai_cache_validation_ttl_seconds,
            "AI_CACHE_L1_MAX_ENTRIES": self.ai_cache_l1_max_entries,
            "AI_CACHE_STAMPEDE_WAIT_SECONDS": self.ai_cache_stampede_wait_seconds,
        }
        if any(value <= 0 for value in positive_numbers.values()):
            invalid = next(name for name, value in positive_numbers.items() if value <= 0)
            raise ValueError(f"{invalid} must be greater than zero")
        if self.openrouter_max_retries < 0 or self.openrouter_max_retries > 5:
            raise ValueError("OPENROUTER_MAX_RETRIES must be between 0 and 5")
        if not 0 <= self.openrouter_confidence_threshold <= 1:
            raise ValueError("OPENROUTER_CONFIDENCE_THRESHOLD must be between 0 and 1")
        for budget in (
            self.openrouter_daily_request_budget,
            self.openrouter_daily_token_budget,
        ):
            if budget is not None and budget <= 0:
                raise ValueError("OpenRouter daily budgets must be greater than zero")
        if self.app_env == "production" and self.ai_cache_enabled and not self.ai_cache_hmac_secret:
            raise ValueError("Production AI caching requires AI_CACHE_HMAC_SECRET")
        operational_positive = {
            "SESSION_TTL_SECONDS": self.session_ttl_seconds,
            "DATA_RETENTION_DAYS": self.data_retention_days,
        }
        if any(value <= 0 for value in operational_positive.values()):
            invalid = next(name for name, value in operational_positive.items() if value <= 0)
            raise ValueError(f"{invalid} must be greater than zero")
        if self.real_data_mode_enabled and (
            not self.data_encryption_key or not self.session_hmac_secret
        ):
            raise ValueError("Real-data mode requires DATA_ENCRYPTION_KEY and SESSION_HMAC_SECRET")
        if self.submission_mode == "production" and not self.production_submission_enabled:
            raise ValueError("Production submission requires PRODUCTION_SUBMISSION_ENABLED=true")
        if self.production_submission_enabled and self.submission_mode != "production":
            raise ValueError(
                "PRODUCTION_SUBMISSION_ENABLED is only valid with SUBMISSION_MODE=production"
            )
        if self.app_env == "production":
            if not self.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
                raise ValueError("Production requires PostgreSQL")
            if self.auth_mode in {"development", "disabled"}:
                raise ValueError("Production requires OIDC or SAML authentication mode")
            if not self.session_secure_cookies:
                raise ValueError("Production requires secure session cookies")
            if self.mock_uat_connector_enabled:
                raise ValueError("The mock UAT connector is forbidden in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


def allowed_origins(configured: str) -> list[str]:
    """Every origin the browser may legitimately arrive from."""
    return [item.strip() for item in configured.split(",") if item.strip()]


def ensure_database_directory(database_url: str) -> None:
    """Create the folder a file-backed SQLite database lives in.

    Alembic builds its own engine and never imports app.persistence.database, so the
    directory has to be created from somewhere both paths reach. Without this, `make
    migrate` fails on a clean clone with "unable to open database file": the folder was
    only ever created as a side effect of importing the application, which the migration
    path does not do — so the second step of the documented setup failed on every new
    machine while working on every machine that had already run the app.
    """
    if not database_url.startswith("sqlite:///"):
        return
    location = database_url.removeprefix("sqlite:///").split("?", 1)[0]
    if location and location != ":memory:":
        Path(location).parent.mkdir(parents=True, exist_ok=True)


def source_path(configured: str, *default: str) -> Path:
    """Resolve one authoritative-source location.

    An empty setting means "the configuration committed to this repository", which is what
    keeps a clean clone working with no environment at all. A relative override is resolved
    against the project root so a drop directory can sit beside the checkout.
    """
    if not configured.strip():
        return CONFIG_ROOT.joinpath(*default)
    candidate = Path(configured.strip()).expanduser()
    return candidate if candidate.is_absolute() else (PROJECT_ROOT / candidate).resolve()
