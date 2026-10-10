
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Server Configuration
    app_env: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    # GitHub Integration
    github_token: str = ""
    github_webhook_secret: str = ""
    target_repo: str = "owner/repo"

    # Gemini LLM API
    gemini_api_key: str = ""

    # Storage & FAISS Index Configuration
    gcs_bucket: str = "codelens-storage"
    local_index_path: str = "./data/indices/faiss_index.bin"
    local_metadata_path: str = "./data/indices/metadata.json"
    feedback_store_path: str = "./data/feedback/reactions.jsonl"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
