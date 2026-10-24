"""Смена гранулярности периода (RUL-PERIOD-GRANULARITY, R36) не теряет банк часов.

Предыдущий период цепочки — тот, что кончается накануне начала текущего, а не
«предыдущий период новой гранулярности»: после month → half_month закрытия 16.09
нет (закрыт весь сентябрь), после half_month → month строка с началом 01.09 — это
первая половина, а банк несёт вторая. Раньше opening() искал по началу периода и
молча брал 0 или банк не той половины (рецензия аудита 22.10.2026, §2.1).

Что проверяется:
  * month → half_month: банк сентября переходит в первую половину октября;
  * half_month → month: банк второй половины сентября переходит в октябрь,
    банк первой половины — нет;
  * незакрытая вторая половина не считается «предыдущий закрыт» для октября;
  * смену гранулярности не с 1-го числа публиковать нельзя.
"""
from __future__ import annotations

import dataclasses
import datetime as dt

import pytest
from sqlalchemy import delete, select

from app.modules.employees.application import Employee
from app.modules.timesheet.adapters.orm import PeriodClosing
from app.modules.timesheet.adapters.sql_bank import SqlBankAdapter
from app.modules.timesheet.adapters.sql_closings import SqlSettlementStore
from app.modules.timesheet.application.months import half_month_period, month_period
from app.modules.timesheet.domain.settings.defaults import default_settings
from app.modules.timesheet.domain.settings.types import GRANULARITY_HALF_MONTH, GRANULARITY_MONTH

SEP, OCT = month_period(2028, 9), month_period(2028, 10)
NOTE = "granularity guard"


class _Settings:
    """Порт настроек с заданной гранулярностью — версии в БД не нужны."""

    def __init__(self, granularity: str):
        self.st = dataclasses.replace(default_settings(), period_granularity=granularity)

    def load(self, period):
        return self.st


@pytest.fixture
def emp(db):
    e = next(e for e in db.scalars(select(Employee)) if "Иванов" in e.display_name)
    yield e
    db.rollback()
    db.execute(delete(PeriodClosing).where(PeriodClosing.employee_id == e.id,
                                           PeriodClosing.period_start >= SEP.start,
                                           PeriodClosing.period_start <= OCT.end))
    db.commit()


def _closed(db, emp, period, bank_minutes: int) -> None:
    db.add(PeriodClosing(employee_id=emp.id, period_start=period.start, period_end=period.end,
                         closing_bank_minutes=bank_minutes, revision=1))
    db.commit()


def test_month_to_half_month_carries_september_bank(db, emp):
    _closed(db, emp, SEP, 120)
    first_half = half_month_period(2028, 10, 1)
    assert SqlBankAdapter(db, _Settings(GRANULARITY_HALF_MONTH)).opening(str(emp.id), first_half) == 120
    state = SqlSettlementStore(db, _Settings(GRANULARITY_HALF_MONTH), "test").period_state(
        str(emp.id), first_half)
    assert state.previous_closed


def test_half_month_to_month_carries_second_half_bank(db, emp):
    _closed(db, emp, half_month_period(2028, 9, 1), 180)
    _closed(db, emp, half_month_period(2028, 9, 2), 480)
    assert SqlBankAdapter(db, _Settings(GRANULARITY_MONTH)).opening(str(emp.id), OCT) == 480


def test_open_second_half_blocks_october(db, emp):
    """Закрыта только первая половина сентября: октябрь закрывать рано."""
    _closed(db, emp, half_month_period(2028, 9, 1), 180)
    state = SqlSettlementStore(db, _Settings(GRANULARITY_MONTH), "test").period_state(str(emp.id), OCT)
    assert not state.previous_closed
    assert SqlBankAdapter(db, _Settings(GRANULARITY_MONTH)).opening(str(emp.id), OCT) == 0


def test_granularity_change_only_from_first_of_month(admin_client, db):
    from app.modules.timesheet.application.catalog import EngineSettingsVersion

    got = admin_client.get("/api/engine-settings").json()
    payload = got["active"]["payload"]
    other = (GRANULARITY_MONTH if payload.get("period_granularity") == GRANULARITY_HALF_MONTH
             else GRANULARITY_HALF_MONTH)
    first = (dt.date.today().replace(day=1) + dt.timedelta(days=400)).replace(day=1)
    body = {"payload": payload | {"period_granularity": other}, "note": NOTE}
    try:
        r = admin_client.put("/api/engine-settings",
                             json=body | {"valid_from": first.replace(day=16).isoformat()})
        assert r.status_code == 422 and "1-го числа" in r.json()["detail"], r.text
        r = admin_client.put("/api/engine-settings", json=body | {"valid_from": first.isoformat()})
        assert r.status_code == 200, r.text
        # та же гранулярность — дата любая (обычная правка настроек)
        r = admin_client.put("/api/engine-settings", json={
            "payload": payload, "note": NOTE, "valid_from": first.replace(day=20).isoformat()})
        assert r.status_code == 422, r.text      # 20-е после смены на other — снова смена
    finally:
        db.execute(delete(EngineSettingsVersion).where(EngineSettingsVersion.note == NOTE))
        db.commit()
