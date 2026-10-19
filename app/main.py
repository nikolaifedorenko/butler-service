"""Точка входа FastAPI: роутеры API + раздача веб-интерфейса (SPA/PWA)."""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .api import (
    access_api,
    audit_api,
    auth_routes,
    cars_api,
    docs_api,
    doublepay,
    employees,
    engine_settings_api,
    fact_api,
    mgmt_api,
    night_api,
    photos_api,
    presence_api,
    punches,
    schedule,
    settings_api,
    tabel_api,
)
from .auth import Principal, optional_principal
from .config import settings
from .db import Base, SessionLocal, engine
from .deps import now_local
from .migrations import (
    migrate_db,
    migrate_engine_v7,
    migrate_manual_replaces_generated,
    migrate_night_cars,
    migrate_night_zones,
    migrate_schedule_dict_simplify,
    migrate_settings_value_text,
    migrate_shift_tabel_codes,
    migrate_time_off_template,
    migrate_timeoff_entity,
    seed_statement_kinds,
)
from .security import new_csrf_token
from .seed import seed_if_empty
from .services.errors import Conflict, Forbidden, Gone, NotFound, Validation

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

def init_db() -> None:
    """Создать таблицы, прогнать миграцию и заполнить демо-данными при первом запуске."""
    Base.metadata.create_all(bind=engine)
    migrate_db()
    migrate_settings_value_text()   # PostgreSQL: шаблоны документов длиннее VARCHAR(255)
    migrate_engine_v7()
    migrate_schedule_dict_simplify()
    seed_statement_kinds()
    db = SessionLocal()
    try:
        seed_if_empty(db)
        from .engine_bootstrap import bootstrap_engine
        bootstrap_engine(db)
        db.commit()
    finally:
        db.close()
    # норматив 12.10.2026 (T1/T4): «код в табеле» у смен — только коды словаря Табеля,
    # «отпросился» и «выходной за часы» — одна запись словаря. Обе миграции идемпотентны
    # и идут ПОСЛЕ bootstrap: первой нужен действующий справочник CFG-DAY-CODES.
    migrate_timeoff_entity()
    migrate_manual_replaces_generated()
    migrate_time_off_template()
    migrate_shift_tabel_codes()
    migrate_night_cars()
    migrate_night_zones()           # зоны обхода (v2): из «категорий» областей
    # ночные смены, пропущенные пока сервер был выключен, + автозакрытие наступивших
    from .night import sync_reports
    from .photos import cleanup_photos

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


@asynccontextmanager
async def lifespan(_: FastAPI):
    _check_secret_key()   # до инициализации БД: не мутируем базу, если ключ не задан
    init_db()
    yield


app = FastAPI(title=settings.app_name, version=settings.app_version, docs_url="/api/docs",
              openapi_url="/api/openapi.json", lifespan=lifespan)

app.add_middleware(GZipMiddleware, minimum_size=1024)


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

# Порядок middleware: регистрируются снизу вверх (последний — самый внешний).
# csrf_protection → security_headers → request_context: заголовки безопасности и
# X-Request-ID попадают и на 403-ответы CSRF-проверки, а метрики/лог видят всё.

_CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# Вход — точка входа: CSRF-cookie у клиента ещё нет, и это отдельная поверхность атаки
# (login-CSRF), поэтому его не проверяем (оба варианта: JSON и form-login с редиректом
# для менеджеров паролей). Остальные mutating-запросы требуют заголовок.
_CSRF_EXEMPT_PATHS = {"/api/auth/login", "/api/auth/login-form"}


def _set_csrf_cookie(response, token: str) -> None:
    response.set_cookie(settings.csrf_cookie_name, token, httponly=False,
                        samesite="lax", path="/", secure=settings.cookie_secure)


@app.middleware("http")
async def csrf_protection(request: Request, call_next):
    """CSRF-защита по схеме double-submit cookie.

    Сессия живёт в httponly-cookie (JS её не видит); CSRF-токен — в отдельной cookie,
    которую JS читает и передаёт в заголовке X-CSRF-Token. Кросс-сайтовый запрос не
    сможет прочитать cookie другого origin, поэтому подделать пару «cookie+заголовок»
    нельзя.

    Токен проверяется ДО вызова обработчика: отклонённый запрос не должен производить
    побочных эффектов. (Проверка после call_next лишь подменяла ответ — действие к
    этому моменту уже было совершено и закоммичено в БД.) Заголовок сравнивается
    побайтово: compare_digest для str с не-ASCII символами бросает TypeError,
    а значение заголовка приходит из сети.
    """
    if not settings.csrf_enabled:
        return await call_next(request)
    token = request.cookies.get(settings.csrf_cookie_name)
    fresh_cookie = token is None
    if fresh_cookie:
        token = new_csrf_token()
    if request.method not in _CSRF_SAFE_METHODS and request.url.path not in _CSRF_EXEMPT_PATHS:
        header = request.headers.get("x-csrf-token", "")
        header_b = header.encode("utf-8", "surrogateescape")
        if fresh_cookie or not header_b or not secrets.compare_digest(header_b, token.encode()):
            # на 403 тоже выдаём cookie: клиент обновится и повторит запрос уже с токеном
            denied = JSONResponse(
                {"detail": "CSRF-проверка не пройдена: обновите страницу и повторите"},
                status_code=403)
            _set_csrf_cookie(denied, token)
            return denied
    response = await call_next(request)
    if fresh_cookie:
        _set_csrf_cookie(response, token)
    return response


# Политика CSP подобрана по фактическому содержимому интерфейса: все скрипты —
# внешние файлы (inline-скриптов и onclick-обработчиков в SPA нет — проверено),
# поэтому script-src строго 'self'. Inline-атрибуты style="…" в шаблонах есть
# (300+) — для них 'unsafe-inline' в style-src (осознанный компромисс без сборки;
# см. docs/adr/0004). data: — SVG-фавикон и иконки селекторов в CSS; blob: —
# скачивание PDF/DOCX через createObjectURL; frame-ancestors дублирует X-Frame-Options.
_CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; "
        "worker-src 'self'; manifest-src 'self'; object-src 'none'; base-uri 'self'; "
        "form-action 'self'; frame-ancestors 'none'")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    h = response.headers
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Referrer-Policy", "same-origin")
    h.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=(), payment=()")
    csp_header = "Content-Security-Policy-Report-Only" if settings.csp_report_only \
        else "Content-Security-Policy"
    h.setdefault(csp_header, _CSP)
    # HSTS имеет смысл только по TLS: за прокси смотрим X-Forwarded-Proto
    # (доверяем ему лишь при TRUST_PROXY_HEADERS — иначе заголовок клиентский),
    # без прокси — схему запроса. По HTTP заголовок браузерами игнорируется,
    # но не рассылаем его зря.
    proto = (request.headers.get("x-forwarded-proto", "") if settings.trust_proxy_headers
             else "") or request.url.scheme
    if proto == "https":
        h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if request.url.path.startswith("/api/") and "cache-control" not in h:
        h["Cache-Control"] = "no-store"   # персональные данные не должны оседать в кэшах
    return response


# ── наблюдаемость: request-id, JSON-лог запросов, метрики Prometheus ──────────
# Метрики — опциональная зависимость: без prometheus_client приложение работает,
# METRICS_ENABLED просто не включить (в requirements.txt пакет есть).
try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

    _HTTP_COUNT = Counter("tt_http_requests_total", "HTTP-запросы по маршрутам",
                          ["method", "route", "status"])
    _HTTP_LATENCY = Histogram("tt_http_request_duration_seconds",
                              "Латентность HTTP-запросов, с", ["method", "route"])
    _PROM_OK = True
except ImportError:          # pragma: no cover - зависит от окружения
    _PROM_OK = False

_access_log = logging.getLogger("butler.access")
if settings.log_json and not _access_log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(message)s"))
    _access_log.addHandler(_h)
    _access_log.setLevel(logging.INFO)
    _access_log.propagate = False

# health опрашивается healthcheck'ами каждые секунды, /metrics — скрейпером:
# в логе запросов это шум без информации
_QUIET_LOG_PATHS = {"/api/health", "/metrics"}
_REQUEST_ID_RE = re.compile(r"[^A-Za-z0-9._-]")


def _observe(request: Request, status: int, started: float, request_id: str) -> None:
    duration_ms = round((time.perf_counter() - started) * 1000.0, 1)
    # метка маршрута — шаблон из роутера (/api/employees/{employee_id}), а не сырой
    # путь: иначе случайные 404-URL раздули бы кардинальность метрик
    label = getattr(request.scope.get("route"), "path", None) or "unmatched"
    if settings.metrics_enabled and _PROM_OK:
        try:
            _HTTP_COUNT.labels(request.method, label, status).inc()
            _HTTP_LATENCY.labels(request.method, label).observe(duration_ms / 1000.0)
        except Exception:   # метрики не должны ронять запрос
            pass
    if settings.log_json and request.url.path not in _QUIET_LOG_PATHS:
        _access_log.info(json.dumps({
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"),
            "method": request.method, "path": request.url.path, "status": status,
            "duration_ms": duration_ms, "route": label, "request_id": request_id,
            "ip": request.client.host if request.client else "-",
        }, ensure_ascii=False))


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Сквозной request-id (от прокси или сгенерированный) + учёт для лога/метрик.

    X-Request-ID возвращается в ответе: по нему один запрос связывается между
    логом приложения, логом прокси и обращением пользователя в поддержку.
    """
    incoming = request.headers.get("x-request-id", "")
    request_id = _REQUEST_ID_RE.sub("", incoming)[:64] or uuid.uuid4().hex[:16]
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        _observe(request, 500, started, request_id)
        raise
    _observe(request, response.status_code, started, request_id)
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/metrics", include_in_schema=False)
def metrics_endpoint():
    """Prometheus-метрики. Включаются METRICS_ENABLED=1; по умолчанию 404 —
    счётчики не должны быть публичными (за прокси доступ можно ограничить по IP)."""
    if not settings.metrics_enabled or not _PROM_OK:
        raise HTTPException(status_code=404, detail="Not found")
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


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
app.include_router(photos_api.router)


def schema_report() -> dict:
    """Полный отчёт о расхождении схемы БД с моделями (для админа и CI)."""
    from sqlalchemy import inspect

    from .models import Base

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
