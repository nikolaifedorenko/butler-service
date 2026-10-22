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

from .bootstrap import registry, schema_version
from .bootstrap.migrations import (
    migrate_db,
    migrate_engine_v7,
    migrate_manual_replaces_generated,
    migrate_night_cars,
    migrate_night_reopened_at,
    migrate_night_zones,
    migrate_schedule_dict_simplify,
    migrate_settings_value_text,
    migrate_time_off_template,
    migrate_timeoff_entity,
    seed_statement_kinds,
)
from .bootstrap.seed import seed_if_empty
from .core import media_api, observability
from .core.auth import Principal, optional_principal
from .core.config import settings
from .core.db import Base, SessionLocal, engine
from .core.errors import Conflict, Forbidden, Gone, NotFound, PayloadTooLarge, Validation
from .core.startup_lock import startup_lock
from .core.time import now_local
from .modules.access.interface import access_api, auth_routes
from .modules.audit.interface import audit_api
from .modules.cars.interface import cars_api
from .modules.docs.interface import docs_api
from .modules.employees.interface import employees
from .modules.night.interface import night_api
from .modules.notify.interface import notify_api
from .modules.settings.interface import settings_api
from .modules.timesheet.application.errors import ApplicationError
from .modules.timesheet.domain.types.errors import ConfigError, DomainError
from .modules.timesheet.interface import (
    doublepay,
    engine_settings_api,
    fact_api,
    mgmt_api,
    presence_api,
    punches,
    schedule,
    tabel_api,
)
from .modules.timesheet.interface.formatting import error_text

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

def init_db() -> None:
    """Создать таблицы, прогнать миграцию и заполнить демо-данными при первом запуске.

    Шаги сериализованы замком (core.startup_lock): прод-профиль поднимает несколько
    воркеров uvicorn (docker-compose.prod.yml), а без сериализации они одновременно
    делают `ALTER TABLE … ADD COLUMN` («duplicate column name» → падение воркера) и
    `sync_reports(force=True)` (IntegrityError по night_reports.date unique) —
    P0-2 ревью 20.10.2026. Второй воркер ждёт первого и повторяет те же идемпотентные
    шаги (секунды); в PostgreSQL замок — advisory-lock, он же держит и несколько
    контейнеров приложения.
    """
    with startup_lock():
        _init_db_steps()


def _init_db_steps() -> None:
    """Тело инициализации схемы — вызывается ТОЛЬКО под замком startup_lock."""
    registry.wire()   # реестр моделей + провайдеры core (R5: core не импортирует модули)
    tables = set(inspect(engine).get_table_names())
    # база до перехода на Alembic (ADR-0002): прежние шаги, затем штамп baseline
    legacy = bool(tables) and "alembic_version" not in tables
    if legacy:
        # shortcut: прежние шаги + create_all текущих моделей верны, пока ревизии после
        # 0001 не создают таблиц и колонок; с первой такой ревизией legacy-ветку удалить
        Base.metadata.create_all(bind=engine)
        migrate_db()
        migrate_settings_value_text()   # PostgreSQL: шаблоны документов длиннее VARCHAR(255)
        migrate_engine_v7()
        migrate_schedule_dict_simplify()
    else:
        schema_version.upgrade()        # пустая база — целиком из ревизий, под Alembic — новые
    seed_statement_kinds()
    db = SessionLocal()
    try:
        seed_if_empty(db)
        from .modules.timesheet.bootstrap import bootstrap_engine
        bootstrap_engine(db)
        db.commit()
    finally:
        db.close()
    if legacy:
        # норматив 12.10.2026 (T1/T4): «код в табеле» у смен — только коды словаря Табеля,
        # «отпросился» и «выходной за часы» — одна запись словаря. Обе миграции идемпотентны
        # и идут ПОСЛЕ bootstrap: первой нужен действующий справочник CFG-DAY-CODES.
        migrate_timeoff_entity()
        migrate_manual_replaces_generated()
        migrate_time_off_template()
        migrate_night_cars()
        migrate_night_zones()           # зоны обхода (v2): из «категорий» областей
        migrate_night_reopened_at()     # момент ручного переоткрытия отчёта (P1 20.10.2026)
        schema_version.stamp_baseline()
        schema_version.upgrade()        # ревизии после baseline
    # ночные смены, пропущенные пока сервер был выключен, + автозакрытие наступивших
    from .core.media import cleanup_photos
    from .modules.night.application.night import sync_reports

    db = SessionLocal()
    try:
        sync_reports(db, force=True)   # при старте — без троттлинга
        cleanup_photos(db)
    finally:
        db.close()


def _weak_secret_key() -> bool:
    """Слабый ключ подписи сессий: пустой, слишком короткий или значение из примера.

    С таким ключом подделать cookie-сессию может кто угодно, поэтому по умолчанию
    старт запрещён; локально его можно разрешить флагом ALLOW_INSECURE_DEV_SECRET=1.
    """
    key = (settings.secret_key or "").strip()
    return len(key) < 16 or key.startswith("change-me")


def _check_secret_key() -> None:
    if not _weak_secret_key():
        return
    msg = (
        "SECRET_KEY не задан или слишком короткий — сессии можно подделать. "
        "Сгенерируйте ключ: python -c \"import secrets; print(secrets.token_hex(32))\" "
        "и пропишите SECRET_KEY в .env / окружение.")
    if settings.allow_insecure_dev_secret:
        import logging
        logging.getLogger("uvicorn.error").warning(msg)
    else:
        raise RuntimeError(msg)


def _check_writable_dirs() -> None:
    """Каталоги данных доступны на запись. Контейнер работает не от root (22.10.2026), а тома,
    созданные раньше, принадлежат root: объясняем, что сделать, вместо непонятной ошибки
    на первой записи в базу SQLite или загрузке фото."""
    import os

    from .core.media import UPLOAD_ROOT
    from .modules.docs.application.doc_render import TEMPLATES_DIR

    bad = [str(d) for d in (UPLOAD_ROOT.parent, TEMPLATES_DIR) if d.exists() and not os.access(d, os.W_OK)]
    if bad:
        raise RuntimeError(f"Нет прав на запись в {', '.join(bad)}. Тома, созданные до запуска "
                           "приложения не от root, один раз передайте пользователю app — "
                           "команда в deploy/README.md §6")


@asynccontextmanager
async def lifespan(_: FastAPI):
    from .bootstrap.night_sync import start_night_sync, stop_night_sync

    _check_secret_key()   # до инициализации БД: не мутируем базу, если ключ не задан
    _check_writable_dirs()
    if settings.migrate_on_start:
        init_db()
    else:
        schema_version.ensure_current()   # миграции сделал сервис migrate (ADR-0002)
    # обслуживание ночных отчётов (досоздание смен, автозакрытие в 08:00) больше не
    # выполняется в GET-запросах — его делает фоновый поток (ревью 20.10.2026, P1);
    # несколько воркеров: раунд выполняет один процесс под замком try_lock
    start_night_sync()
    try:
        yield
    finally:
        stop_night_sync()


def _docs_urls() -> dict:
    """Swagger и схема API — только при API_DOCS=1; ReDoc не используется (OPS-04)."""
    on = settings.api_docs
    return {"docs_url": "/api/docs" if on else None,
            "openapi_url": "/api/openapi.json" if on else None, "redoc_url": None}


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan,
              **_docs_urls())

app.add_middleware(GZipMiddleware, minimum_size=1024)
registry.wire()   # реестр моделей + провайдеры core — до первого запроса (и для тестов без init_db)


# ── маппинг доменных ошибок сервисного слоя в HTTP ──────────────────────────
# Сервисы (app/services/*) не знают про FastAPI и бросают services.errors.*;
# тело ответа прежнее — {"detail": текст}, контракты API и тесты не меняются.
@app.exception_handler(NotFound)
async def _not_found_handler(request: Request, exc: NotFound):
    return JSONResponse({"detail": str(exc)}, status_code=404)


@app.exception_handler(Forbidden)
async def _forbidden_handler(request: Request, exc: Forbidden):
    return JSONResponse({"detail": str(exc)}, status_code=403)


@app.exception_handler(Validation)
async def _validation_handler(request: Request, exc: Validation):
    return JSONResponse({"detail": str(exc)}, status_code=422)


@app.exception_handler(Conflict)
async def _conflict_handler(request: Request, exc: Conflict):
    return JSONResponse({"detail": str(exc)}, status_code=409)


@app.exception_handler(Gone)
async def _gone_handler(request: Request, exc: Gone):
    return JSONResponse({"detail": str(exc)}, status_code=410)


@app.exception_handler(PayloadTooLarge)
async def _payload_too_large_handler(request: Request, exc: PayloadTooLarge):
    """Файл больше настроенного лимита (фото/видео) → 413."""
    return JSONResponse({"detail": str(exc)}, status_code=413)


# ── маппинг типизированных ошибок расчётного движка (EXECUTION-SPEC-v2 §5.3) ──
# Домены модулей бросают типизированные исключения (DomainError/ConfigError/
# ApplicationError); человеческий текст собирается в interface-слое модуля
# (error_text), роутерам запрещается ловить доменные ошибки «для красивого
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
# (тесты) — см. docs/CHANGES-2026-10-20-stage-c2-timesheet.md.
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


app.include_router(auth_routes.router)
app.include_router(employees.router)
app.include_router(schedule.router)
app.include_router(punches.router)
app.include_router(tabel_api.router)
app.include_router(mgmt_api.router)
app.include_router(presence_api.router)
app.include_router(fact_api.router)
app.include_router(access_api.router)
app.include_router(audit_api.router)
app.include_router(engine_settings_api.router)
app.include_router(settings_api.router)
app.include_router(docs_api.router)
app.include_router(doublepay.router)
app.include_router(night_api.router)
app.include_router(cars_api.router)
app.include_router(notify_api.router)
app.include_router(media_api.router)


def schema_report() -> dict:
    """Полный отчёт о расхождении схемы БД с моделями (для админа и CI)."""
    from sqlalchemy import inspect

    from .core.db import Base

    insp = inspect(engine)
    db_tables = set(insp.get_table_names())
    missing: list[str] = []
    for table in Base.metadata.sorted_tables:
        if table.name not in db_tables:
            missing.append(f"таблица {table.name}")
            continue
        have = {c["name"] for c in insp.get_columns(table.name)}
        for column in table.columns:
            if column.name not in have:
                missing.append(f"{table.name}.{column.name}")
    return {
        "ok": not missing,
        "missing": missing,
        "tables_expected": len(Base.metadata.sorted_tables),
        "tables_found": len(db_tables & {t.name for t in Base.metadata.sorted_tables}),
        "app": settings.app_name,
        "hint": "" if not missing else
                "Схема БД старее кода: остановите сервер и запустите снова (миграция применится при старте). "
                "Если не помогло — удалите timetrack.db (демо) или восстановите базу из бэкапа (боевая).",
    }


@app.get("/api/selfcheck")
def selfcheck(principal: Optional[Principal] = Depends(optional_principal)):
    """Самодиагностика: соответствует ли схема БД моделям текущего кода.

    Список таблиц и колонок берётся из Base.metadata (models.py) — единственного
    источника правды. Раньше здесь был второй рукописный список, который уже
    разошёлся с migrate_db(): шесть добавленных колонок (включая users.token_version)
    не проверялись, и selfcheck не мог заметить отставание схемы.

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
               "server_time_local": now_local().isoformat(timespec="seconds"),
               "server_time_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
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


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


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
