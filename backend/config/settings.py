"""Environment-driven settings loader.

All runtime configuration is read from environment variables (via ``.env``) into a
single typed :class:`Settings` object. No connection details, model names, or secrets
are hardcoded in source. Required settings fail fast at load time — before any request
is served — rather than surfacing as errors mid-request.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings loaded from the environment / ``.env``.

    Contract: required credentials (``database_url``, ``anthropic_api_key``,
    ``openai_api_key``) have no defaults, so a missing value raises a
    ``pydantic.ValidationError`` at construction. Model names, FinX base URLs, and
    tracing flags carry safe defaults and are overridable via the environment.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Required (fail-fast, no default) ---
    database_url: str = Field(..., alias="DATABASE_URL")
    anthropic_api_key: str = Field(..., alias="ANTHROPIC_API_KEY")
    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")

    # --- Models (overridable) ---
    anthropic_model: str = Field("claude-sonnet-4-5", alias="ANTHROPIC_MODEL")
    embedding_model: str = Field("text-embedding-3-large", alias="EMBEDDING_MODEL")

    # --- FinX report APIs (CML and Contract Note live on different hosts) ---
    finx_cml_base_url: str = Field(
        "https://finxomne.choiceindia.com", alias="FINX_CML_BASE_URL"
    )
    finx_contract_note_base_url: str = Field(
        "https://finx.choiceindia.com", alias="FINX_CONTRACT_NOTE_BASE_URL"
    )

    # --- Tracing (optional; no-op when unset) ---
    confident_api_key: str | None = Field(None, alias="CONFIDENT_API_KEY")
    tracing_enabled: bool = Field(False, alias="TRACING_ENABLED")

    # --- CORS (POC frontend origins; comma-separated, "*" allows any) ---
    cors_origins: str = Field("*", alias="CORS_ORIGINS")

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse ``cors_origins`` into a list of allowed origins ("*" -> ["*"])."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return the cached :class:`Settings` singleton (constructed on first call)."""
    return Settings()  # type: ignore[call-arg]
