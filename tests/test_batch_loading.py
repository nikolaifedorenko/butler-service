"""Пакетная загрузка Табеля и Факта (аудит, шаг 6.4, PERF-02): одним запросом на весь штат
вместо запросов на каждого сотрудника. Ответы обязаны совпадать с прежними точечными.

* lock_marks/lock_states — те же closed и next_closed, что period_state: правило блокировки
  периода одно (open / last_closed / locked).
* prefetch отметок и занятости — те же marks_between, last_mark_before и employment.
"""
from __future__ import annotations

import datetime as dt

from app.core.time import local_date

D = dt.date


def test_lock_states_match_period_state(db):
    from app.modules.employees.application import Employee
    from app.modules.timesheet.adapters.orm import PeriodClosing
    from app.modules.timesheet.application import timesheet_edit
    from app.modules.timesheet.application.engine_common import engine_ports
    from app.modules.timesheet.domain.types.entities import Period

    a, b, c = db.query(Employee).filter(Employee.deleted_at.is_(None)).order_by(Employee.id).limit(3)
    march, april = Period(D(2031, 3, 1), D(2031, 3, 31)), Period(D(2031, 4, 1), D(2031, 4, 30))
    rows = [PeriodClosing(employee_id=a.id, period_start=march.start, period_end=march.end),
            PeriodClosing(employee_id=b.id, period_start=march.start, period_end=march.end),
            PeriodClosing(employee_id=b.id, period_start=april.start, period_end=april.end)]
    db.add_all(rows)
    db.commit()
    try:
        ports = engine_ports(db)
        ids = [str(a.id), str(b.id), str(c.id)]
        assert timesheet_edit.lock_states(ids, D(2031, 3, 10), ports) == {
            str(a.id): "last_closed", str(b.id): "locked", str(c.id): "open"}
        for e in ids:
            st = ports.store.period_state(e, march)
            assert ports.store.lock_marks(ids, march)[e] == (st.closed, st.next_closed)
        assert timesheet_edit.lock_state(str(b.id), D(2031, 4, 2), ports) == "last_closed"
    finally:
        for r in rows:
            db.delete(r)
        db.commit()


def test_prefetch_gives_same_marks_and_employment(db):
    from app.core.time import TZ
    from app.modules.employees.application import Employee
    from app.modules.timesheet.application.engine_common import engine_ports
    from app.modules.timesheet.domain.types.entities import Period

    today = local_date()
    first = today.replace(day=1)
    lo = dt.datetime.combine(first, dt.time(0), TZ)
    hi = dt.datetime.combine(today + dt.timedelta(days=1), dt.time(0), TZ)
    ids = [str(e.id) for e in db.query(Employee).filter(Employee.deleted_at.is_(None))]
    plain, batched = engine_ports(db), engine_ports(db)
    batched.punch.prefetch(ids, lo, hi)
    batched.employment.prefetch(ids)
    seen = 0
    for e in ids:
        marks = plain.punch.marks_between(e, lo, hi)
        assert batched.punch.marks_between(e, lo, hi) == marks
        assert batched.punch.last_mark_before(e, lo) == plain.punch.last_mark_before(e, lo)
        period = Period(first, today)
        assert batched.employment.employment(e, period) == plain.employment.employment(e, period)
        seen += len(marks)
    assert seen, "в демо-данных нет отметок за месяц — сравнение ничего не проверяет"
