"""Отметка задним числом видит сессию, открытую накануне (рецензия аудита 22.10.2026, P1).

Направление «auto» при корректировке определялось по отметкам окна [дата отметки 00:00,
+2 дня): ночной «Пришёл» накануне в окно не попадал, и «Ушёл» в 00:30 становился вторым
«Пришёл». Явный «Пришёл» задним числом при открытой на тот момент сессии тоже проходил.
Открытая сессия на момент ts — та же, что у кнопок (_open_session, ADR-0009): последняя
отметка до ts — «пришёл».
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import delete, select

from app.core.time import local_date

NOTE = "проба backfill"


@pytest.fixture()
def night_in(db):
    """Иванов «пришёл» накануне в 23:50 (три дня назад); корректировка — в 00:30."""
    from app.modules.employees.application.catalog import Employee
    from app.modules.timesheet.adapters.orm import Punch

    emp = db.scalar(select(Employee).where(Employee.full_name.like("Иванов%")))
    day = local_date() - dt.timedelta(days=3)
    p = Punch(employee_id=emp.id, ts=dt.datetime.combine(day, dt.time(23, 50)), kind="IN",
              source="manual", note=NOTE)
    db.add(p)
    db.commit()
    yield emp, dt.datetime.combine(day + dt.timedelta(days=1), dt.time(0, 30))
    db.execute(delete(Punch).where(Punch.employee_id == emp.id, Punch.note == NOTE))
    db.commit()


def test_auto_backfill_closes_session_opened_yesterday(manager_client, night_in, db):
    from app.modules.timesheet.adapters.orm import Punch

    emp, ts = night_in
    r = manager_client.post("/api/punches", json={
        "employee_id": emp.id, "kind": "auto", "ts": ts.isoformat(timespec="minutes"), "note": NOTE})
    assert r.status_code == 200, r.text
    added = db.scalar(select(Punch).where(Punch.employee_id == emp.id, Punch.ts == ts))
    assert added is not None and added.kind == "OUT"


def test_explicit_backfill_in_into_open_session_is_409(manager_client, night_in):
    emp, ts = night_in
    r = manager_client.post("/api/punches", json={
        "employee_id": emp.id, "kind": "in", "ts": ts.isoformat(timespec="minutes"), "note": NOTE})
    assert r.status_code == 409 and "23:50" in r.json()["detail"], r.text
