"""Точка входа FastAPI: роутеры API + раздача веб-интерфейса (SPA/PWA)."""
from __future__ import annotations

import datetime as dt
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import (
    auth_routes,
    cars_api,
    docs_api,
    doublepay,
    employees,
    night_api,
    photos_api,
    punches,
    schedule,
    settings_api,
    timesheet,
)
from .config import settings
from .db import Base, SessionLocal, engine
from .deps import now_local
from .migrations import migrate_db, migrate_night_cars, seed_statement_kinds
from .seed import seed_if_empty

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

def init_db() -> None:
    """Создать таблицы, прогнать миграцию и заполнить демо-данными при первом запуске."""
    Base.metadata.create_all(bind=engine)
    migrate_db()
    seed_statement_kinds()
    db = SessionLocal()
    try:
        seed_if_empty(db)
    finally:
        db.close()
    migrate_night_cars()
    # ночные смены, пропущенные пока сервер был выключен, + автозакрытие наступивших
    from .night import sync_reports
    from .photos import cleanup_photos

    db = SessionLocal()
    try:
        sync_reports(db)
        cleanup_photos(db)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if settings.secret_key.startswith("change-me"):
        import logging
        logging.getLogger("uvicorn.error").warning(
            "SECRET_KEY не задан (используется значение по умолчанию)! Сессии можно подделать. "
            "Сгенерируйте ключ: python -c \"import secrets; print(secrets.token_hex(32))\" "
            "и пропишите SECRET_KEY в .env / окружение.")
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", docs_url="/api/docs",
              openapi_url="/api/openapi.json", lifespan=lifespan)

app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    h = response.headers
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Referrer-Policy", "same-origin")
    if request.url.path.startswith("/api/") and "cache-control" not in h:
        h["Cache-Control"] = "no-store"   # персональные данные не должны оседать в кэшах
    return response


app.include_router(auth_routes.router)
app.include_router(employees.router)
app.include_router(schedule.router)
app.include_router(punches.router)
app.include_router(timesheet.router)
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
