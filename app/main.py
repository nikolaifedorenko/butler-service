"""Точка входа FastAPI: роутеры API + раздача веб-интерфейса (SPA/PWA)."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import (auth_routes, cars_api, docs_api, doublepay, employees, night_api,
                  punches, schedule, settings_api, timesheet)
from .config import settings
from .db import Base, engine, SessionLocal
from .deps import now_local
from .seed import seed_if_empty

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

def migrate_db() -> None:
    """Лёгкая миграция: добавляет новые колонки/таблицы и переносит данные,
    чтобы ранее созданные локальные БД продолжали работать после обновления.

    Что делает текущая версия:
      * роли: senior → supervisor;
      * блоки: «Администрация» → «Пятидневка» (+ индивидуальный шаблон выходных);
      * сотрудники: гражданство, служба/подразделение;
      * словарь смен: архивация вместо удаления, ревизии, «списывать из банка», тип документа;
      * ячейки графика: частичное отсутствие (отпросился с … до …);
      * табель: несогласованные перерывы и часы согласованного отсутствия;
      * периоды работы (приём → увольнение → повторный приём);
      * корректировки банка часов;
      * дни двойной оплаты (производственный календарь) и периоды ВИП-гостей:
        таблицы double_pay_days / vip_double_pay и колонки ДЯ2/ДН2 в табеле.
    """
    import json

    from sqlalchemy import inspect, text

    insp = inspect(engine)
    additions = {
        "employees": [
            ("tab_number", "VARCHAR(40) DEFAULT ''"),
            ("hired_at", "DATE"),
            ("emergency_name", "VARCHAR(200) DEFAULT ''"),
            ("emergency_phone", "VARCHAR(40) DEFAULT ''"),
            ("schedule_pattern", "VARCHAR(60) DEFAULT ''"),
            ("schedule_anchor", "DATE"),
            ("deleted_at", "DATE"),
            ("telegram", "VARCHAR(64) DEFAULT ''"),
            ("email", "VARCHAR(120) DEFAULT ''"),
            ("dismissed_at", "DATE"),
            ("full_name_genitive", "VARCHAR(220) DEFAULT ''"),
            ("nationality", "VARCHAR(120) DEFAULT ''"),
            ("subdivision", "VARCHAR(160) DEFAULT ''"),
        ],
        "timesheet_rows": [
            ("pay_ot_day", "FLOAT DEFAULT 0"),
            ("pay_ot_night", "FLOAT DEFAULT 0"),
            ("late_hours", "FLOAT DEFAULT 0"),
            ("early_hours", "FLOAT DEFAULT 0"),
            ("unused_hours", "FLOAT DEFAULT 0"),
            ("gap_hours", "FLOAT DEFAULT 0"),
            ("auth_hours", "FLOAT DEFAULT 0"),
            ("pay_ot_day2", "FLOAT DEFAULT 0"),
            ("pay_ot_night2", "FLOAT DEFAULT 0"),
            ("double_reason", "VARCHAR(16) DEFAULT ''"),
        ],
        "shift_types": [
            ("deduct_from_bank", "BOOLEAN DEFAULT 0"),
            ("doc_type", "VARCHAR(40) DEFAULT ''"),
            ("archived_at", "DATE"),
            ("punch_in_allowed", "BOOLEAN DEFAULT 1"),
            ("punch_out_allowed", "BOOLEAN DEFAULT 1"),
        ],
        "schedule_entries": [
            ("partial_shift_id", "INTEGER"),
            ("from_time", "VARCHAR(5) DEFAULT ''"),
            ("until_time", "VARCHAR(5) DEFAULT ''"),
            ("punch_in_override", "BOOLEAN"),
            ("punch_out_override", "BOOLEAN"),
        ],
        "block_assignments": [
            ("pattern_json", "TEXT DEFAULT ''"),
        ],
        "users": [
            ("token_version", "INTEGER DEFAULT 0"),
        ],
    }
    with engine.begin() as con:
        for table, cols in additions.items():
            if not insp.has_table(table):
                continue
            have = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in cols:
                if name not in have:
                    con.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))

        if insp.has_table("users"):
            con.execute(text("UPDATE users SET role='supervisor' WHERE role='senior'"))
        if insp.has_table("punches"):
            # основной фильтр всех запросов по отметкам: employee_id = ? AND ts >= ?
            con.execute(text("CREATE INDEX IF NOT EXISTS ix_punches_emp_ts ON punches (employee_id, ts)"))

        # «Администрация» → «Пятидневка» (название блока уточнили по смыслу)
        if insp.has_table("employees"):
            con.execute(text("UPDATE employees SET schedule_group='Пятидневка' "
                             "WHERE schedule_group='Администрация'"))
        if insp.has_table("block_assignments"):
            con.execute(text('UPDATE block_assignments SET "group"=:new '
                             'WHERE "group"=:old'), {"new": "Пятидневка", "old": "Администрация"})

        # вид отсутствий, по которому печатаем документ, и списание часов с банка
        if insp.has_table("shift_types"):
            for code, doc_type in (("VACATION", "vacation_paid"),
                                   ("VACATION_UNPAID", "vacation_unpaid"),
                                   ("TIMEOFF_HOURS", "day_off_hours"),
                                   ("AWAY_HOURS", "time_off_request")):
                con.execute(text("UPDATE shift_types SET doc_type=:dt "
                                 "WHERE code=:c AND (doc_type IS NULL OR doc_type='')"),
                            {"dt": doc_type, "c": code})
            con.execute(text("UPDATE shift_types SET deduct_from_bank=1 "
                             "WHERE code IN ('TIMEOFF_HOURS','AWAY_HOURS') "
                             "AND (deduct_from_bank IS NULL OR deduct_from_bank=0)"))

        # сотрудники без записей блоков получают открытую запись от даты приёма
        if insp.has_table("employees") and insp.has_table("block_assignments"):
            con.execute(text("""
                INSERT INTO block_assignments (employee_id, "group", start_date, end_date, pattern_json)
                SELECT e.id, e.schedule_group, COALESCE(e.hired_at, '2020-01-01'), NULL, ''
                FROM employees e
                WHERE e.schedule_group <> '' AND e.deleted_at IS NULL
                  AND NOT EXISTS (SELECT 1 FROM block_assignments b WHERE b.employee_id = e.id)
            """))

        # справочник служб/подразделений: заполняем существующими значениями из карточек
        if insp.has_table("employees") and insp.has_table("subdivisions"):
            con.execute(text("""
                INSERT INTO subdivisions (name)
                SELECT DISTINCT e.subdivision FROM employees e
                WHERE e.subdivision <> ''
                  AND NOT EXISTS (SELECT 1 FROM subdivisions s WHERE s.name = e.subdivision)
            """))

    # старым базам докладываем новые смены словаря (например «Отпросился» — AWAY_HOURS)
    _migrate_missing_shifts()
    # периоды работы (приём → увольнение → повторный приём)
    _migrate_employment_periods()
    # индивидуальный шаблон пятидневки: берём выходные из общих настроек (как было раньше)
    _migrate_fiveday_patterns()
    # общий шаблон блоков в настройках: переименовываем ключ «Администрация»
    _migrate_base_groups_key()


def _migrate_missing_shifts() -> None:
    """Старым базам докладываем отсутствующие смены из словаря сида (например AWAY_HOURS
    «Отпросился: отсутствовал часть смены»). Существующие смены НЕ трогаются."""
    from sqlalchemy import inspect, text

    from .seed import SHIFT_EXTRA, SHIFT_TYPES

    insp = inspect(engine)
    if not insp.has_table("shift_types"):
        return
    with engine.begin() as con:
        # свежую базу заполняет сид (seed_if_empty) — не дублируем его здесь
        if insp.has_table("users"):
            users = con.execute(text("SELECT COUNT(*) FROM users")).scalar() or 0
            if not users:
                return
        have = {r[0] for r in con.execute(text("SELECT code FROM shift_types"))}
        for (code, name, disp, tzh, kind, start, end, overnight, color, order,
             is_work, counted, default_off) in SHIFT_TYPES:
            if code in have:
                continue
            extra = SHIFT_EXTRA.get(code, {})
            con.execute(text("""
                INSERT INTO shift_types (code, name, display_code, tzh_code, kind, start_time, end_time,
                    overnight, color, sort_order, is_working, counts_as_worked, is_default_off, active,
                    deduct_from_bank, doc_type, archived_at)
                VALUES (:code, :name, :disp, :tzh, :kind, :start, :end, :overnight, :color, :order,
                    :is_work, :counted, :default_off, 1, :deduct, :doc_type, NULL)
            """), {"code": code, "name": name, "disp": disp, "tzh": tzh, "kind": kind,
                   "start": start, "end": end, "overnight": int(bool(overnight)), "color": color,
                   "order": order, "is_work": int(bool(is_work)), "counted": int(bool(counted)),
                   "default_off": int(bool(default_off)),
                   "deduct": int(bool(extra.get("deduct_from_bank", False))),
                   "doc_type": extra.get("doc_type", "")})


def _migrate_employment_periods() -> None:
    """Создать периоды работы по hired_at/dismissed_at (один раз, при переходе на новую схему)."""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if not (insp.has_table("employment_periods") and insp.has_table("employees")):
        return
    with engine.begin() as con:
        con.execute(text("""
            INSERT INTO employment_periods (employee_id, start_date, end_date, note, created_at)
            SELECT e.id,
                   COALESCE(e.hired_at, '2020-01-01'),
                   CASE WHEN e.dismissed_at IS NOT NULL AND e.active = 0 THEN e.dismissed_at ELSE NULL END,
                   'восстановлено по дате приёма/увольнения',
                   CURRENT_TIMESTAMP
            FROM employees e
            WHERE NOT EXISTS (SELECT 1 FROM employment_periods p WHERE p.employee_id = e.id)
        """))
        # уволенные: открытый период блока закрываем датой увольнения (последний рабочий день)
        con.execute(text("""
            UPDATE block_assignments
            SET end_date = (SELECT e.dismissed_at FROM employees e WHERE e.id = block_assignments.employee_id)
            WHERE end_date IS NULL
              AND employee_id IN (SELECT id FROM employees
                                  WHERE dismissed_at IS NOT NULL AND active = 0 AND deleted_at IS NULL)
        """))


def _migrate_fiveday_patterns() -> None:
    """Пятидневка: перенести выходные из общих настроек в шаблон каждого сотрудника,
    чтобы дальше выходные можно было задавать индивидуально (вс/пн, пт/сб, сб/вс…)."""
    import json

    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if not (insp.has_table("block_assignments") and insp.has_table("settings")):
        return
    with engine.begin() as con:
        row = con.execute(text("SELECT value FROM settings WHERE key='base_groups'")).first()
        off_weekdays, shift_code = [5, 6], "DAY9"
        if row and row[0]:
            try:
                groups = json.loads(row[0])
                cfg = groups.get("Пятидневка") or groups.get("Администрация") or {}
                off_weekdays = cfg.get("off_weekdays") or off_weekdays
                shift_code = cfg.get("shift_code") or shift_code
            except (json.JSONDecodeError, AttributeError):
                pass
        con.execute(text("""
            UPDATE block_assignments
            SET pattern_json = :pj
            WHERE "group" = 'Пятидневка' AND (pattern_json IS NULL OR pattern_json = '')
        """), {"pj": json.dumps({"kind": "week5", "off_weekdays": off_weekdays,
                                 "shift_code": shift_code}, ensure_ascii=False)})


def _migrate_base_groups_key() -> None:
    import json

    from sqlalchemy import text

    with engine.begin() as con:
        row = con.execute(text("SELECT value FROM settings WHERE key='base_groups'")).first()
        if not row or not row[0]:
            return
        try:
            groups = json.loads(row[0])
        except json.JSONDecodeError:
            return
        if "Администрация" in groups and "Пятидневка" not in groups:
            groups["Пятидневка"] = groups.pop("Администрация")
            con.execute(text("UPDATE settings SET value=:v WHERE key='base_groups'"),
                        {"v": json.dumps(groups, ensure_ascii=False)})


def _seed_statement_kinds() -> None:
    """Словарь видов заявлений: при первом запуске новой версии добавляем встроенные
    виды (тексты — из сохранённых настроек, иначе дефолтные). Если словарь уже
    заполнен — не вмешиваемся (удалённые пользователем виды не воскрешаем)."""
    from sqlalchemy import func, select

    from .doc_render import DOC_TYPES
    from .doc_templates import load_doc_templates
    from .models import StatementKind

    db = SessionLocal()
    try:
        if db.scalar(select(func.count(StatementKind.id))):
            return
        doc = load_doc_templates(db)
        legacy_text = {
            "vacation_paid": doc["vacation"],
            "vacation_unpaid": doc["vacation_unpaid"],
            "day_off_hours": doc["day_off_hours"],
            "time_off_request": doc["time_off_request"],
        }
        order = 10
        for code, name in DOC_TYPES.items():
            db.add(StatementKind(code=code, name=name, text=legacy_text.get(code, ""),
                                 builtin=True, sort_order=order))
            order += 10
        db.commit()
    finally:
        db.close()


def _migrate_night_cars() -> None:
    """Старым локальным БД докладываем таблицы ночных отчётов и электрокаров.

    Новые таблицы создаёт Base.metadata.create_all, но в SQLite у create_all нет
    if-not-exists для индексов на уже существующих таблицах — поэтому всё делаем
    аккуратно, по inspect. Полноту схемы проверяет /api/selfcheck."""
    from sqlalchemy import inspect as sa_inspect, text

    insp = sa_inspect(engine)
    with engine.begin() as con:
        for idx in (
            "CREATE INDEX IF NOT EXISTS ix_night_sections_report ON night_area_sections (report_id)",
            "CREATE INDEX IF NOT EXISTS ix_night_items_section ON night_check_items (section_id)",
            "CREATE INDEX IF NOT EXISTS ix_car_history_car_ts ON car_history (car_id, ts)",
            "CREATE INDEX IF NOT EXISTS ix_photos_kind_ref ON photos (kind, ref_id)",
        ):
            try:
                con.execute(text(idx))
            except Exception:   # таблица ещё не создана — create_all разберётся сам
                pass
    # шаг «Проверка электрокаров» для старых открытых смен, где его не было
    if insp.has_table("night_reports") and insp.has_table("night_area_sections"):
        from .night import CAR_AREA_NAME

        with engine.begin() as con:
            con.execute(text("""
                INSERT INTO night_area_sections (report_id, area_id, name, category, snapshot_json,
                                                sort_order, status)
                SELECT r.id, NULL, :name, 'cars', '[]', 900, 'free'
                FROM night_reports r
                WHERE NOT EXISTS (SELECT 1 FROM night_area_sections s
                                  WHERE s.report_id = r.id AND s.category = 'cars')
            """), {"name": CAR_AREA_NAME})


def init_db() -> None:
    """Создать таблицы, прогнать миграцию и заполнить демо-данными при первом запуске."""
    Base.metadata.create_all(bind=engine)
    migrate_db()
    _seed_statement_kinds()
    db = SessionLocal()
    try:
        seed_if_empty(db)
    finally:
        db.close()
    _migrate_night_cars()
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


@app.get("/api/selfcheck")
def selfcheck():
    """Самодиагностика: хватает ли схеме БД колонок/таблиц текущей версии кода."""
    from sqlalchemy import inspect

    from .models import Base  # noqa: F401

    insp = inspect(engine)
    missing: list[str] = []
    required = {
        "employees": ["telegram", "email", "dismissed_at", "tab_number", "hired_at",
                      "schedule_group", "group_color", "deleted_at", "schedule_pattern",
                      "nationality", "subdivision", "full_name_genitive"],
        "timesheet_rows": ["pay_ot_day", "pay_ot_night", "late_hours", "early_hours", "ot_note",
                           "gap_hours", "auth_hours", "pay_ot_day2", "pay_ot_night2",
                           "double_reason"],
        "shift_types": ["deduct_from_bank", "doc_type", "archived_at"],
        "schedule_entries": ["partial_shift_id", "from_time", "until_time"],
        "block_assignments": ["pattern_json"],
        "users": ["role"],
    }
    tables = set(insp.get_table_names())
    for table in ("block_assignments", "position_history", "emergency_contacts",
                  "employment_periods", "bank_adjustments", "shift_revisions",
                  "double_pay_days", "vip_double_pay",
                  "night_areas", "checklist_items", "night_reports", "night_area_sections",
                  "night_check_items", "night_interceptions", "car_locations", "cars",
                  "car_history", "car_night_checks", "photos"):
        if table not in tables:
            missing.append(f"таблица {table}")
    for table, cols in required.items():
        if table not in tables:
            missing.append(f"таблица {table}")
            continue
        have = {c["name"] for c in insp.get_columns(table)}
        for col in cols:
            if col not in have:
                missing.append(f"{table}.{col}")
    return {
        "ok": not missing,
        "missing": missing,
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
