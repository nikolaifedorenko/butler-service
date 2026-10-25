"""Конфигурация приложения (читается из .env / переменных окружения)."""
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Батлер Сервис — учёт рабочего времени"
    # Адрес БД, по старшинству (25.10.2026):
    #   1. DATABASE_URL — как задан;
    #   2. POSTGRES_HOST (+ POSTGRES_USER/PASSWORD/DB/PORT) — адрес собирается здесь, с
    #      экранированием: раньше compose подставлял пароль в URL как есть, и «@ : / # %»
    #      в пароле ломали подключение (рецензия аудита 22.10.2026);
    #   3. SQLite-файл SQLITE_PATH (в образе — внутри тома data/, см. Dockerfile).
    database_url: str = ""
    postgres_host: str = ""
    postgres_port: int = 5432
    postgres_user: str = "timetrack"
    postgres_password: str = ""
    postgres_db: str = "timetrack"
    sqlite_path: str = "./timetrack.db"
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
    # 1 — воркер при старте сам мигрирует схему и готовит данные (локально, демо-compose);
    # 0 — только сверяет ревизию: миграции делает отдельный шаг python -m app.bootstrap.migrate
    migrate_on_start: bool = True
    # Swagger /api/docs и схема /api/openapi.json; в проде 0 — полная карта API без входа
    # облегчает разведку (OPS-04). Схему для разработки отдаёт tools/export_openapi.py.
    api_docs: bool = True
    # семантическая версия приложения: bump при релизе (тег + запись в CHANGELOG.md)
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
    # ключ Fernet шифрования секретов уведомлений в БД (токен бота, пароль SMTP);
    # "новый,старый" — смена ключа (app/modules/notify/application/secrets.py, 25.10.2026)
    notify_secret_key: str = ""

    @model_validator(mode="after")
    def _resolve_database_url(self) -> "Settings":
        if not self.database_url:
            self.database_url = postgres_url(self) if self.postgres_host else f"sqlite:///{self.sqlite_path}"
        return self


def postgres_url(s: "Settings") -> str:
    """postgresql+psycopg2://… из POSTGRES_*. Строку собирает сам SQLAlchemy (URL.create):
    экранирование всегда то, которое разбирает установленная версия — ручной quote() имя
    базы на одних версиях раскодировался, на других нет (CI, Python 3.10)."""
    from sqlalchemy.engine import URL

    return URL.create("postgresql+psycopg2", username=s.postgres_user,
                      password=s.postgres_password or None, host=s.postgres_host,
                      port=s.postgres_port, database=s.postgres_db
                      ).render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
