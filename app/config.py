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
    # cookie с CSRF-токеном (double-submit): читается JS и передаётся в заголовке X-CSRF-Token
    csrf_cookie_name: str = "tt_csrf"
    # CSRF-защита включена; в тестах отключается (CSRF_ENABLED=0) — TestClient не имитирует браузер
    csrf_enabled: bool = True
    # ставьте 1, когда сайт работает по HTTPS: cookie будет передаваться только по TLS
    cookie_secure: bool = False
    # demo-режим: разрешить менеджеру «войти как сотрудник» без пароля
    allow_impersonation: bool = True
    # разрешить запуск со слабым/пустым SECRET_KEY — ТОЛЬКО для локальной разработки.
    # В остальных случаях приложение откажется стартовать (см. app/main.py).
    allow_insecure_dev_secret: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
