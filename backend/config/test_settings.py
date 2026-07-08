"""Tests for the FinX middleware base URL setting."""

import pytest

from backend.config.settings import get_settings


@pytest.fixture(autouse=True)
def _settings_env(monkeypatch):
    """Provide the required settings env so ``get_settings()`` constructs cleanly."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("FINX_MIDDLEWARE_BASE_URL", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_finx_middleware_base_url_default():
    assert get_settings().finx_middleware_base_url == "https://finx.choiceindia.com"


def test_finx_middleware_base_url_override(monkeypatch):
    monkeypatch.setenv("FINX_MIDDLEWARE_BASE_URL", "https://staging.finx.example.com")
    get_settings.cache_clear()
    assert get_settings().finx_middleware_base_url == "https://staging.finx.example.com"
