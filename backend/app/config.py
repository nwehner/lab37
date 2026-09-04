from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ORDER_MGMT_", env_file=".env", extra="ignore")

    database_url: str = f"sqlite:///{BACKEND_DIR / 'order_management.db'}"
    polling_enabled: bool = True
    polling_api_base_url: str = "http://localhost:8001"
    polling_interval_seconds: float = 30.0
    polling_backoff_initial_seconds: float = 5.0
    polling_backoff_max_seconds: float = 300.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
