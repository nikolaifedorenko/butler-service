"""Гигиена по рецензии аудита (P3, решения владельца 25.10.2026).

Что проверяется:
  * начальный пароль: сгенерированный возвращается один раз, введённый — нет;
  * массовое внесение в Табель и «Назначить отсутствие» — «всё или ничего»;
  * картинка принимается только по содержимому, не по расширению;
  * сессия принимается только с типом токена session;
  * на SQLite включена проверка внешних ключей;
  * публикация настроек: одновременная вторая публикация ждёт первую и получает 409;
  * удаление кода Табеля сверяется с версией настроек на дату новой версии.
"""
from __future__ import annotations

import datetime as dt
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text

from app.core.time import local_date

NOTE = "P3 гигиена"


def _month_start(d: dt.date, back: int) -> dt.date:
    y, m = d.year, d.month - back
    while m < 1:
        y, m = y - 1, m + 12
    return dt.date(y, m, 1)


# ── начальный пароль ────────────────────────────────────────────────────────────────

def test_generated_password_shown_once_typed_one_not_echoed(app_stack, admin_client):
    r = admin_client.post("/api/employees", json={
        "full_name": "Паролев Сгенерированный", "position": "Батлер", "role": "employee",
        "hired_at": local_date().isoformat(), "schedule_group": "Смена 1", "username": "p3_gen"})
    assert r.status_code == 200, r.text
    generated = r.json()["initial_password"]
    assert generated and len(generated) >= 8
    c = TestClient(app_stack["app"])
    assert c.post("/api/auth/login", json={"username": "p3_gen", "password": generated}).status_code == 200

    r = admin_client.post("/api/employees", json={
        "full_name": "Паролев Введённый", "position": "Батлер", "role": "employee",
        "hired_at": local_date().isoformat(), "schedule_group": "Смена 1", "username": "p3_typed",
        "password": "TypedPass-2026"})
    assert r.status_code == 200 and r.json()["initial_password"] is None, r.text


# ── «всё или ничего»: Табель и «Назначить отсутствие» ──────────────────────────────────

@pytest.fixture()
def frozen_month(db):
    """У Иванова закрыты два прошлых месяца: позапрошлый «заморожен» (правки — 409),
    прошлый — последний закрытый (правки разрешены). Дни: [последний замороженного,
    1-е и 2-е прошлого]; снимок Табеля этих дней — до теста."""
    from app.modules.employees.application.catalog import Employee
    from app.modules.timesheet.adapters.orm import PeriodClosing, TabelDay

    emp = db.scalar(select(Employee).where(Employee.full_name.like("Иванов%")))
    m2, m1, m0 = (_month_start(local_date(), k) for k in (2, 1, 0))
    have = set(db.scalars(select(PeriodClosing.period_start).where(PeriodClosing.employee_id == emp.id)))
    rows = [PeriodClosing(employee_id=emp.id, period_start=s, period_end=e)
            for s, e in ((m2, m1 - dt.timedelta(days=1)), (m1, m0 - dt.timedelta(days=1)))
            if s not in have]
    db.add_all(rows)
    db.commit()
    days = [m1 - dt.timedelta(days=1), m1, m1 + dt.timedelta(days=1)]

    def snapshot():
        db.expire_all()
        return [(r.date, r.code, r.plan_minutes, r.note) for r in db.scalars(
            select(TabelDay).where(TabelDay.employee_id == emp.id, TabelDay.date.in_(days))
            .order_by(TabelDay.date))]
    yield emp, days, snapshot
    for r in rows:
        db.delete(db.get(PeriodClosing, r.id))
    db.commit()


def test_tabel_bulk_all_or_nothing(admin_client, frozen_month):
    emp, days, snapshot = frozen_month
    before = snapshot()
    r = admin_client.post("/api/tabel/bulk", json={"employee_ids": [emp.id],
                                                   "dates": [d.isoformat() for d in days],
                                                   "code": "ОТ", "note": NOTE})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is False and out["written"] == 0
    assert [e["date"] for e in out["errors"]] == [days[0].isoformat()]
    assert snapshot() == before, "часть ячеек записалась при ошибке в другой"


def test_range_absence_all_or_nothing(admin_client, frozen_month):
    emp, days, snapshot = frozen_month
    before = snapshot()
    r = admin_client.post("/api/schedule/range-absence", json={
        "employee_ids": [emp.id], "first": days[0].isoformat(), "last": days[-1].isoformat(),
        "code": "ОТ", "note": NOTE})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is False and out["written"] == 0
    assert days[0].isoformat() in [e["date"] for e in out["errors"]]
    assert snapshot() == before


# ── медиа, токен, внешние ключи ───────────────────────────────────────────────────────

def test_image_accepted_only_by_content():
    from app.core.media import sniff_media

    assert sniff_media(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32, "shot.png") == ("photo", "png")
    assert sniff_media(b"#!/bin/sh\necho hi\n", "evil.jpg") == ("", ""), "файл с именем .jpg — не фото"
    heic = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00heicmif1" + b"\x55" * 16
    assert sniff_media(heic, "IMG_0001.HEIC") == ("", ""), "HEIC — как и раньше, отклоняется"


def test_session_requires_session_token_type(app_stack, db):
    from app.core.config import settings
    from app.core.identity import User
    from app.core.security import create_token

    user = db.scalar(select(User).where(User.username == "ivanov"))
    body = {"uid": user.id, "emp_id": user.employee_id, "tv": int(user.token_version or 0)}
    for token, expected in ((create_token(body), 401),                      # без типа
                            (create_token(body | {"typ": "reset"}), 401),   # чужой тип
                            (create_token(body | {"typ": "session"}), 200)):
        c = TestClient(app_stack["app"])
        c.cookies.set(settings.cookie_name, token)
        assert c.get("/api/auth/me").status_code == expected


def test_sqlite_enforces_foreign_keys(app_stack):
    from app.core.db import engine

    if engine.dialect.name != "sqlite":
        pytest.skip("PostgreSQL проверяет внешние ключи всегда")
    with engine.connect() as con:
        assert con.execute(text("PRAGMA foreign_keys")).scalar() == 1


# ── публикация настроек ───────────────────────────────────────────────────────────────

@pytest.fixture()
def cleanup_versions(db):
    yield
    from app.modules.timesheet.application.catalog import EngineSettingsVersion

    db.rollback()
    db.execute(delete(EngineSettingsVersion).where(EngineSettingsVersion.note == NOTE))
    db.commit()


def test_concurrent_publish_waits_and_gets_409(app_stack, admin_client, cleanup_versions):
    """Первая публикация держит замок; вторая — от той же базовой версии — ждёт её и
    получает 409, а не проходит рядом (раньше сверка и вставка не были атомарны)."""
    from fastapi import HTTPException

    from app.modules.timesheet.application.catalog import EngineSettingsVersion
    from app.modules.timesheet.interface.engine_settings_api import _lock_and_check_base_version

    SessionLocal = app_stack["SessionLocal"]
    base = admin_client.get("/api/engine-settings").json()["latest_id"]
    outcome: list = []
    done = threading.Event()

    def second():
        with SessionLocal() as s:
            try:
                _lock_and_check_base_version(s, base)
                outcome.append("passed")
            except HTTPException as exc:
                outcome.append(exc.status_code)
            finally:
                s.rollback()
                done.set()

    with SessionLocal() as first:
        _lock_and_check_base_version(first, base)              # первая взяла замок
        first.add(EngineSettingsVersion(valid_from=dt.date(2031, 1, 1), payload_json="{}", note=NOTE,
                                        created_by_name="тест"))
        first.flush()
        t = threading.Thread(target=second)
        t.start()
        time.sleep(0.5)
        assert not done.is_set(), "вторая публикация не ждёт первую"
        first.commit()
    t.join(timeout=15)
    assert outcome == [409], outcome


def test_removed_day_code_checked_against_version_on_its_date(admin_client, db, cleanup_versions):
    """Код, который есть только в будущей версии и уже стоит в Табеле: версия ещё позже
    без него — 422. Раньше сверка шла с версией «на сегодня», где кода нет, и проходила."""
    from app.modules.employees.application.catalog import Employee
    from app.modules.timesheet.adapters.orm import TabelDay

    got = admin_client.get("/api/engine-settings").json()
    payload = got["active"]["payload"]
    with_code = json.loads(json.dumps(payload))
    with_code["day_code_policy"]["ТСТ"] = dict(with_code["day_code_policy"]["В"])
    first = (local_date().replace(day=1) + dt.timedelta(days=400)).replace(day=1)
    r = admin_client.put("/api/engine-settings", json={
        "valid_from": first.isoformat(), "payload": with_code, "note": NOTE, "base_version_id": got["latest_id"]})
    assert r.status_code == 200, r.text
    emp = db.scalar(select(Employee).where(Employee.full_name.like("Иванов%")))
    db.add(TabelDay(employee_id=emp.id, date=first + dt.timedelta(days=3), code="ТСТ", plan_minutes=0,
                    source="manual"))
    db.commit()
    try:
        later = (first + dt.timedelta(days=40)).replace(day=1)
        r = admin_client.put("/api/engine-settings", json={
            "valid_from": later.isoformat(), "payload": payload, "note": NOTE,
            "base_version_id": admin_client.get("/api/engine-settings").json()["latest_id"]})
        assert r.status_code == 422 and "ТСТ" in r.json()["detail"], r.text
    finally:
        db.execute(delete(TabelDay).where(TabelDay.employee_id == emp.id, TabelDay.code == "ТСТ"))
        db.commit()
