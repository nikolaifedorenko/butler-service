"""Закрытие периода и правки входа — под одной блокировкой сотрудника (рецензия аудита
22.10.2026, P1, TOCTOU).

close_period читал вход (load_inputs) до транзакции сохранения: на PostgreSQL (READ
COMMITTED) отметка или правка Табеля, закоммиченная между чтением и записью результата,
в закрытый результат не попадала — без следа. Теперь закрытие и пересчёт берут
lock_employee ДО чтения, а все писатели входа (отметки, Табель, График, банк) — ту же
блокировку: писатель ждёт закрытия, закрытие — писателя.

Что проверяется:
  * close_period и recalculate блокируют сотрудника раньше, чем читают вход;
  * писатели Табеля, Графика и отметок ждут, пока блокировку держит закрытие.
"""
from __future__ import annotations

import datetime as dt
import threading
import time

import pytest
from sqlalchemy import delete, select

from app.modules.timesheet.application.close_period import close_period
from app.modules.timesheet.application.recalculate import recalculate
from tests.engine.helpers import EMP, at
from tests.engine.test_application import OCT, _stand

READS = ("timesheet.days", "punch.marks_between")


def _lock_before_reads(queries: list) -> None:
    lock = queries.index("store.lock_employee")
    assert all(lock < queries.index(q) for q in READS if q in queries), queries


def test_close_and_recalculate_lock_before_reading_inputs():
    db, ports = _stand()
    close_period(EMP, OCT, at(1, 0, month=11), ports)
    _lock_before_reads(db.queries)
    db.queries.clear()
    recalculate(EMP, OCT, at(2, 0, month=11), ports)
    _lock_before_reads(db.queries)


# ── реальная БД: писатель входа ждёт, пока блокировку держит закрытие ──────────────

DAY = dt.date(2029, 4, 9)


@pytest.fixture
def emp_id(db):
    from app.modules.employees.application import Employee
    from app.modules.timesheet.adapters.orm import Punch, ScheduleAbsence, TabelDay

    emp = next(e for e in db.scalars(select(Employee)) if "Иванов" in e.display_name)
    yield emp.id
    db.rollback()
    lo = dt.datetime.combine(DAY, dt.time(0))
    db.execute(delete(TabelDay).where(TabelDay.employee_id == emp.id, TabelDay.date == DAY))
    db.execute(delete(ScheduleAbsence).where(ScheduleAbsence.employee_id == emp.id,
                                             ScheduleAbsence.start_utc >= lo - dt.timedelta(days=1),
                                             ScheduleAbsence.start_utc < lo + dt.timedelta(days=2)))
    db.execute(delete(Punch).where(Punch.employee_id == emp.id, Punch.ts >= lo,
                                   Punch.ts < lo + dt.timedelta(days=1)))
    db.commit()


def _tabel(s, emp):
    from app.modules.timesheet.adapters.sql_timesheet_store import SqlTimesheetStore
    SqlTimesheetStore(s).save_day(str(emp), DAY, "В", 0)


def _absence(s, emp):
    from app.core.time import TZ
    from app.modules.timesheet.adapters.sql_schedule import SqlScheduleStore
    SqlScheduleStore(s, TZ).save_absence(str(emp), DAY, "10:00", "12:00", False)


def _punch_lock(s, emp):
    """Отметка: та же блокировка, что в _punch_locked (+ сама запись)."""
    from app.core.db import lock_employee
    from app.modules.timesheet.adapters.orm import Punch
    lock_employee(s, emp)
    s.add(Punch(employee_id=emp, ts=dt.datetime.combine(DAY, dt.time(9)), kind="IN", source="manual"))


@pytest.mark.parametrize("write", [_tabel, _absence, _punch_lock], ids=["tabel", "absence", "punch"])
def test_input_writer_waits_for_closing_lock(app_stack, emp_id, write):
    from app.modules.timesheet.adapters.sql_closings import SqlSettlementStore

    SessionLocal = app_stack["SessionLocal"]
    done = threading.Event()
    errors: list = []

    def writer():
        with SessionLocal() as s:
            try:
                write(s, emp_id)
                s.commit()
            except Exception as exc:          # pragma: no cover — видно в assert ниже
                errors.append(exc)
            finally:
                done.set()

    with SessionLocal() as closing:
        SqlSettlementStore(closing, None).lock_employee(str(emp_id))   # «закрытие» держит
        t = threading.Thread(target=writer)
        t.start()
        time.sleep(0.5)
        assert not done.is_set(), "писатель входа не ждёт блокировку закрытия"
        closing.commit()
    t.join(timeout=10)
    assert done.is_set() and not errors, errors
