"""Конфигурация приложения (читается из .env / переменных окружения)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Батлер Сервис — учёт рабочего времени"
    database_url: str = "sqlite:///./timetrack.db"
    secret_key: str = "change-me-in-production"
    app_tz: str = "Europe/Moscow"
    # срок жизни сессии: 48 ч (было 14 суток) — короткое окно для украденной cookie;
    # переопределяется SESSION_TTL_HOURS
    session_ttl_hours: int = 48
    cookie_name: str = "tt_session"
    # cookie с CSRF-токеном (double-submit): читается JS и передаётся в заголовке X-CSRF-Token
    csrf_cookie_name: str = "tt_csrf"
    # CSRF-защита включена; в тестах отключается (CSRF_ENABLED=0) — TestClient не имитирует браузер
    csrf_enabled: bool = True
    # ставьте 1, когда сайт работает по HTTPS: cookie будет передаваться только по TLS
    cookie_secure: bool = False
    # demo-режим: разрешить менеджеру «войти как сотрудник» без пароля.
    # Включён ПО УМОЛЧАНИЮ — решение владельца от 15.10.2026: функция нужна
    # в повседневной работе (демонстрация интерфейса, поддержка сотрудников).
    # Отключается ALLOW_IMPERSONATION=0 на стендах, где она не нужна.
    allow_impersonation: bool = True
    # читать IP клиента (rate-limit входа) из X-Forwarded-For — включать ТОЛЬКО
    # за своим доверенным reverse-proxy, иначе заголовок подделывается клиентом.
    trust_proxy_headers: bool = False
    # CSP в режиме Report-Only (браузер предупреждает в консоли, но не блокирует) —
    # для осторожного раскатывания; 0 — полноценный блокирующий режим.
    csp_report_only: bool = False
    # наблюдаемость: JSON-лог запросов (метод/путь/статус/длительность/request-id)
    # вместо человечного; для прода за прокси (uvicorn --no-access-log в compose)
    log_json: bool = False
    # /metrics (Prometheus): по умолчанию выключен — метрики не должны быть публичными
    metrics_enabled: bool = False
    # семантическая версия приложения: bump при релизе (тег + docs/CHANGES-*.md)
    app_version: str = "0.1.0"
    # разрешить запуск со слабым/пустым SECRET_KEY — ТОЛЬКО для локальной разработки.
    # В остальных случаях приложение откажется стартовать (см. app/main.py).
    allow_insecure_dev_secret: bool = False
    # фоновая синхронизация ночных отчётов (bootstrap/night_sync.py): досоздание
    # наступивших смен и автозакрытие в 08:00 больше НЕ выполняются в GET-запросах
    # (ревью 20.10.2026, P1) — их делает фоновый поток с периодом night_sync_seconds.
    # Несколько воркеров: в раунде работает один (замок core.startup_lock.try_lock).
    night_sync_enabled: bool = True
    night_sync_seconds: int = 60
    # пустая база: DEMO_SEED=1 — демо-сотрудники с паролем demo1234 (локально, тесты, сценарии);
    # иначе только справочники и администратор admin с паролем ADMIN_PASSWORD (аудит, SEC-02)
    demo_seed: bool = False
    admin_password: str = ""
    # адрес Telegram Bot API (корпоративный прокси); из UI не меняется — иначе токен бота
    # уходит на любой хост (аудит 21.10.2026, SEC-03). Пусто — сохранённый или api.telegram.org
    notify_telegram_api: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
