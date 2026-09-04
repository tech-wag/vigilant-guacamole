"""
Centralized configuration. Everything the app needs from the environment
is validated here once, at import time, so a missing/malformed var fails
fast on startup instead of deep inside a webhook handler.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # GitHub
    github_token: str
    github_webhook_secret: str
    github_repo: str  # "owner/repo"

    # Claude
    anthropic_api_key: str
    claude_model: str = "claude-sonnet-5"

    # App behavior
    max_diff_bytes: int = 200_000
    log_level: str = "INFO"
    db_path: str = "runs.db"


@lru_cache
def get_settings() -> Settings:
    """Cached so Settings() is only constructed/validated once per process."""
    return Settings()
