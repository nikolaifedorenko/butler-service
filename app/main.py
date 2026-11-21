"""Точка входа FastAPI: роутеры API + раздача веб-интерфейса (SPA/PWA)."""
from __future__ import annotations

import datetime as dt
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from .bootstrap import metrics as state_metrics
from .bootstrap import modules, registry, schema_version
from .bootstrap.seed import seed_if_empty, seed_statement_kinds
from .core import observability
from .core.auth import Principal, optional_principal
from .core.config import settings
from .core.db import SessionLocal, engine
from .core.errors import ServiceError
from .core.startup_lock import startup_lock
from .core.time import local_iso, local_now
from .modules.timesheet.application.errors import ApplicationError
from .modules.timesheet.application.texts import error_text
from .modules.timesheet.domain.types.errors import ConfigError, DomainError

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

def init_db() -> None:
    """Создать таблицы, прогнать миграцию и заполнить демо-данными при первом запуске.

    Шаги сериализованы замком (core.startup_lock): прод-профиль поднимает несколько
    воркеров uvicorn (docker-compose.prod.yml), а без сериализации они одновременно
    делают `ALTER TABLE … ADD COLUMN` («duplicate column name» → падение воркера) и
    `sync_reports(force=True)` (IntegrityError по night_reports.date unique) —
    Второй воркер ждёт первого и повторяет те же идемпотентные
    шаги (секунды); в PostgreSQL замок — advisory-lock, он же держит и несколько
    контейнеров приложения.
    """
    with startup_lock():
        _init_db_steps()


def _init_db_steps() -> None:
    """Тело инициализации схемы — вызывается ТОЛЬКО под замком startup_lock."""
    registry.wire()   # реестр моделей + провайдеры core (R5: core не импортирует модули)
    schema_version.upgrade()            # пустая база — целиком из ревизий, остальные — новыми
    seed_statement_kinds()
    db = SessionLocal()
    try:
        seed_if_empty(db)
        from .modules.timesheet.bootstrap import bootstrap_engine
        bootstrap_engine(db)
        from .modules.notify.application.config import SECRET_KEYS
        from .modules.notify.application.secrets import encrypt_stored_secrets
        encrypt_stored_secrets(db, SECRET_KEYS)   # открытые секреты → шифротекст, смена ключа
        db.commit()
    finally:
        db.close()
    # ночные смены, пропущенные пока сервер был выключен, + автозакрытие наступивших
    from .core.media import cleanup_photos
    from .modules.night.application.night import sync_reports

    db = SessionLocal()
    try:
        sync_reports(db, force=True)   # при старте — без троттлинга
        cleanup_photos(db)
    finally:
        db.close()


def _check_writable_dirs() -> None:
    """Каталоги данных доступны на запись. Контейнер работает не от root, а тома,
    созданные раньше, принадлежат root: объясняем, что сделать, вместо непонятной ошибки
    на первой загрузке фото или бланка."""
    import os

    from .core.media import UPLOAD_ROOT
    from .modules.exchange.application.documents import TEMPLATES_DIR

    bad = [str(d) for d in (UPLOAD_ROOT.parent, TEMPLATES_DIR) if d.exists() and not os.access(d, os.W_OK)]
    if bad:
        raise RuntimeError(f"Нет прав на запись в {', '.join(bad)}. Тома, созданные до запуска "
                           "приложения не от root, один раз передайте пользователю app — "
                           "команда в deploy/README.md §6")


@asynccontextmanager
async def lifespan(_: FastAPI):
    from .modules.notify.application.secrets import check_key_config
    check_key_config()    # NOTIFY_SECRET_KEY задан, но не разбирается — отказ на старте
    _check_writable_dirs()
    if settings.migrate_on_start:
        init_db()
    else:
        schema_version.ensure_current()   # миграции сделал сервис migrate (ADR-0002)
    yield


def _docs_urls() -> dict:
    """Swagger и схема API — только при API_DOCS=1; ReDoc не используется."""
    on = settings.api_docs
    return {"docs_url": "/api/docs" if on else None,
            "openapi_url": "/api/openapi.json" if on else None, "redoc_url": None}


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan,
              **_docs_urls())

app.add_middleware(GZipMiddleware, minimum_size=1024)
registry.wire()   # реестр моделей + провайдеры core — до первого запроса (и для тестов без init_db)


# ── ошибки прикладного слоя → HTTP ──────────────────────────────────────────
# Прикладной слой не знает про FastAPI и бросает наследников ServiceError (core/errors.py):
# статус задаёт класс ошибки, тело — {"detail": текст или словарь}.
@app.exception_handler(ServiceError)
async def _service_error_handler(request: Request, exc: ServiceError):
    return JSONResponse(exc.body, status_code=exc.status_code)


# ── маппинг типизированных ошибок расчётного движка (EXECUTION-SPEC-v2 §5.3) ──
# Домены модулей бросают типизированные исключения (DomainError/ConfigError/
# ApplicationError); человеческий текст собирает прикладной слой модуля
# (application/texts.py, error_text), роутерам запрещается ловить доменные ошибки «для красивого
# текста». Статусы:
#   ConfigError → 409 — повреждённая конфигурация есть СОСТОЯНИЕ системы
#     (типизированный отказ вкладок, не 500; закреплено
#     tests/test_timesheet_norm.py::test_10_config_error_is_409_not_500).
#     Редактор настроек (PUT /api/engine-settings) валидирует ВВОД и оставляет
#     локальный catch → 422 (закреплено test_engine_api::test_engine_settings_validation);
#   DomainError → 422 — невалидные входные данные запроса;
#   ApplicationError → 409 — конфликт состояния (период закрыт и т.п.).
# Прим.: §5.3 спеки предписывал 422 для ConfigError, но §11.1 требует побайтового
# сохранения статусов, закреплённых тестами; приоритет у более конкретного текста
# (тесты) — см. docs/archive/changes/CHANGES-2026-10-20-stage-c2-timesheet.md.
@app.exception_handler(ConfigError)
async def _engine_config_error_handler(request: Request, exc: ConfigError):
    return JSONResponse({"detail": error_text(exc)}, status_code=409)


@app.exception_handler(DomainError)
async def _engine_domain_error_handler(request: Request, exc: DomainError):
    return JSONResponse({"detail": error_text(exc)}, status_code=422)


@app.exception_handler(ApplicationError)
async def _engine_application_error_handler(request: Request, exc: ApplicationError):
    return JSONResponse({"detail": error_text(exc)}, status_code=409)

# Middleware (CSRF, заголовки безопасности/CSP, request-id/лог/метрики) и /metrics
# переехали в core/observability.py (фаза C1): main.py — composition root.
# Порядок регистрации сохранён (см. docstring observability.register).
observability.register(app)
state_metrics.register()


# роутеры — из манифестов модулей (ADR-0012), в порядке order
modules.include_routers(app, modules.discover())


_SCHEMA_HINT = ("Схема БД старее кода: остановите сервер и запустите снова (миграция применится при "
                "старте). Если не помогло — пересоздайте демо-базу (docker compose down -v) или "
                "восстановите боевую из бэкапа.")
_INDEX_HINT = ("Не созданы защитные уникальные индексы — запрет дублей в базе не действует (например, "
               "«один сотрудник — один кар»). Миграция пропускает такой индекс, если в данных уже есть "
               "дубли, и пишет об этом в лог (строки «0004:», «0009:»). Устраните дубли и выполните "
               "команду из перечня — повторный запуск миграции индекс не создаст.")


def schema_report() -> dict:
    """Полный отчёт о расхождении схемы БД с моделями (для админа и CI).

    Таблицы, колонки и уникальные индексы моделей. Индексы тоже: без индекса защита
    «один сотрудник — один кар» молча не работает, а самопроверка писала бы «схема в порядке»."""
    from sqlalchemy.schema import CreateIndex

    from .core.db import Base

    insp = inspect(engine)
    db_tables = set(insp.get_table_names())
    missing: list[str] = []
    missing_indexes: list[str] = []
    for table in Base.metadata.sorted_tables:
        if table.name not in db_tables:
            missing.append(f"таблица {table.name}")
            continue
        have = {c["name"] for c in insp.get_columns(table.name)}
        for column in table.columns:
            if column.name not in have:
                missing.append(f"{table.name}.{column.name}")
        have_idx = {i["name"] for i in insp.get_indexes(table.name)}
        for index in sorted((i for i in table.indexes if i.unique and i.name), key=lambda i: str(i.name)):
            if index.name not in have_idx:
                sql = str(CreateIndex(index).compile(dialect=engine.dialect)).strip()
                missing_indexes.append(f"индекс {index.name} ({table.name}: "
                                       f"{', '.join(c.name for c in index.columns)}) — {sql}")
    hint = _SCHEMA_HINT if missing else _INDEX_HINT if missing_indexes else ""
    return {
        "ok": not missing and not missing_indexes,
        "missing": missing + missing_indexes,
        "missing_indexes": len(missing_indexes),
        "tables_expected": len(Base.metadata.sorted_tables),
        "tables_found": len(db_tables & {t.name for t in Base.metadata.sorted_tables}),
        "app": settings.app_name,
        "hint": hint,
    }


@app.get("/api/selfcheck")
def selfcheck(principal: Optional[Principal] = Depends(optional_principal)):
    """Самодиагностика: соответствует ли схема БД моделям текущего кода.

    Список таблиц и колонок берётся из Base.metadata (models.py) — единственного
    источника правды (раньше был второй рукописный список, и он расходился со схемой).

    Без входа (так проверку показывает инструкция по установке) отдаётся только
    итог ok/hint; перечень таблиц и колонок — лишь администратору: схема БД —
    полезная разведка для атакующего.
    """
    full = schema_report()
    if principal is not None and principal.is_admin:
        return full
    return {"ok": full["ok"], "app": full["app"], "hint": full["hint"],
            "details": "" if full["ok"] else "перечень расхождений доступен администратору"}


@app.get("/api/health")
def health():
    """Liveness + readiness: 200, если приложение отвечает и БД доступна;
    503 — если БД недоступна (healthcheck контейнера/балансировщика должен падать,
    harнессы готовности это используют). Детали ошибки БД наружу не отдаются —
    только тип исключения: в сообщении могут быть данные подключения."""
    db_state = "ok"
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception as exc:
        db_state = f"error: {type(exc).__name__}"
    payload = {"ok": db_state == "ok", "app": settings.app_name,
               "version": settings.app_version, "db": db_state, "tz": settings.app_tz,
               "server_time_local": local_iso(local_now()),
               "server_time_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds")}
    return JSONResponse(payload, status_code=200 if payload["ok"] else 503)


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    """Service Worker отдаётся с корня (scope = «/») и без кэша — иначе обновления не доедут."""
    return FileResponse(str(STATIC_DIR / "sw.js"), media_type="application/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return FileResponse(str(STATIC_DIR / "manifest.webmanifest"), media_type="application/manifest+json",
                        headers={"Cache-Control": "no-cache"})


class RevalidatingStaticFiles(StaticFiles):
    """Статика с обязательной перепроверкой (ETag → 304). Скрипты-модули подключают друг друга по
    адресу без ?v=, поэтому браузер не должен держать устаревшую копию по эвристике Last-Modified."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/static", RevalidatingStaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/{full_path:path}")
def spa(full_path: str):
    """Все не-API маршруты отдают index.html (клиентский роутинг)."""
    if full_path.startswith("api/"):
        return JSONResponse({"detail": "Not found"}, status_code=404)
    # защита от path traversal («/css%2f..%2f..%2f.env»): после нормализации путь
    # обязан остаться внутри static/ — иначе отдаём index.html, как для любого SPA-маршрута
    candidate = (STATIC_DIR / full_path).resolve()
    if full_path and candidate.is_file() and candidate.is_relative_to(STATIC_DIR.resolve()):
        return FileResponse(str(candidate))
    # index.html не кешируем: иначе браузер может держать старую версию с прежними app.js/css
    return FileResponse(str(STATIC_DIR / "index.html"),
                        headers={"Cache-Control": "no-store, must-revalidate"})
