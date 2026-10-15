"""Точка входа FastAPI: роутеры API + раздача веб-интерфейса (SPA/PWA)."""
from __future__ import annotations

import datetime as dt
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

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
from .config import settings
from .db import Base, SessionLocal, engine
from .deps import now_local
from .migrations import (
    migrate_db,
    migrate_engine_v7,
    migrate_night_cars,
    migrate_shift_tabel_codes,
    migrate_timeoff_entity,
    seed_statement_kinds,
)
from .security import new_csrf_token
from .seed import seed_if_empty

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

def init_db() -> None:
    """Создать таблицы, прогнать миграцию и заполнить демо-данными при первом запуске."""
    Base.metadata.create_all(bind=engine)
    migrate_db()
    migrate_engine_v7()
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
    migrate_shift_tabel_codes()
    migrate_night_cars()
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


app = FastAPI(title=settings.app_name, version="0.1.0", docs_url="/api/docs",
              openapi_url="/api/openapi.json", lifespan=lifespan)

app.add_middleware(GZipMiddleware, minimum_size=1024)


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


_CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# Вход — точка входа: CSRF-cookie у клиента ещё нет, и это отдельная поверхность атаки
# (login-CSRF), поэтому его не проверяем. Остальные mutating-запросы требуют заголовок.
_CSRF_EXEMPT_PATHS = {"/api/auth/login"}


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


@app.get("/api/selfcheck")
def selfcheck():
    """Самодиагностика: соответствует ли схема БД моделям текущего кода.

    Список таблиц и колонок берётся из Base.metadata (models.py) — единственного
    источника правды. Раньше здесь был второй рукописный список, который уже
    разошёлся с migrate_db(): шесть добавленных колонок (включая users.token_version)
    не проверялись, и selfcheck не мог заметить отставание схемы.
    """
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


@app.get("/api/health")
def health():
    return {"ok": True, "app": settings.app_name, "tz": settings.app_tz,
            "server_time_local": now_local().isoformat(timespec="seconds"),
            "server_time_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}


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
