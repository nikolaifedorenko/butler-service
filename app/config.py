"""Конфигурация приложения (читается из .env / переменных окружения)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Батлер Сервис — учёт рабочего времени"
    database_url: str = "sqlite:///./timetrack.db"
    secret_key: str = "change-me-in-production"
    app_tz: str = "Europe/Moscow"
    session_ttl_hours: int = 24 * 14
    cookie_name: str = "tt_session"
    # ставьте 1, когда сайт работает по HTTPS: cookie будет передаваться только по TLS
    cookie_secure: bool = False
    # demo-режим: разрешить менеджеру «войти как сотрудник» без пароля
    allow_impersonation: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
