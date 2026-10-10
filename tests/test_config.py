from src.config import Settings, get_settings


def test_default_settings():
    settings = Settings(_env_file=None)
    assert settings.app_env == "development"
    assert settings.port == 8000
    assert settings.gcs_bucket == "codelens-storage"
    assert settings.target_repo == "owner/repo"


def test_custom_settings_via_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PORT", "9000")
    monkeypatch.setenv("GITHUB_TOKEN", "test_token_123")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini_key_456")

    custom_settings = Settings(_env_file=None)
    assert custom_settings.app_env == "production"
    assert custom_settings.port == 9000
    assert custom_settings.github_token == "test_token_123"
    assert custom_settings.gemini_api_key == "gemini_key_456"



def test_get_settings_singleton():
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
