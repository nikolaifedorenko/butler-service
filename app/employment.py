"""Периоды работы сотрудника: приём → увольнение → повторный приём.

Дата увольнения считается ПОСЛЕДНИМ РАБОЧИМ ДНЁМ (включительно), дата повторного приёма —
ПЕРВЫМ рабочим днём. Между периодами сотрудник в графике неактивен (ячейки «—»),
но вся история (табель, отметки, документы) сохраняется.
"""
from __future__ import annotations

import datetime as dt
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Employee, EmploymentPeriod, utcnow


def ensure_periods(db: Session, emp: Employee) -> list[EmploymentPeriod]:
    """Если периодов ещё нет (старая база) — создать один по hired_at/dismissed_at."""
    recs = list(db.scalars(select(EmploymentPeriod).where(
        EmploymentPeriod.employee_id == emp.id).order_by(EmploymentPeriod.start_date)))
    if recs:
        return recs
    start = emp.hired_at or dt.date(2020, 1, 1)
    period = EmploymentPeriod(employee_id=emp.id, start_date=start,
                              end_date=emp.dismissed_at if not emp.active else None,
                              note="восстановлено по дате приёма/увольнения")
    db.add(period)
    db.flush()
    return [period]


def periods_of(db: Session, emp_id: int) -> list[EmploymentPeriod]:
    return list(db.scalars(select(EmploymentPeriod).where(
        EmploymentPeriod.employee_id == emp_id).order_by(EmploymentPeriod.start_date)))


def employed_on(periods: Iterable[EmploymentPeriod], date: dt.date) -> bool:
    return any(p.start_date <= date and (p.end_date is None or p.end_date >= date) for p in periods)


def is_employed(db: Session, emp: Employee, date: dt.date) -> bool:
    return employed_on(periods_of(db, emp.id), date)


def employed_ranges(db: Session, emp_id: int, first: dt.date, last: dt.date) -> list[dict]:
    """Периоды работы, обрезанные по границам месяца (для «неактивных» ячеек графика)."""
    out = []
    for p in periods_of(db, emp_id):
        s = max(p.start_date, first)
        e = min(p.end_date, last) if p.end_date else last
        if s <= e:
            out.append({"start": s.isoformat(), "end": e.isoformat(),
                        "open": p.end_date is None, "note": p.note or ""})
    return out


def open_period(db: Session, emp: Employee, since: dt.date, note: str = "",
                user_id: Optional[int] = None) -> EmploymentPeriod:
    """Новый период работы (приём или повторный приём после увольнения)."""
    cur = db.scalar(select(EmploymentPeriod).where(
        EmploymentPeriod.employee_id == emp.id,
        EmploymentPeriod.end_date.is_(None)).order_by(EmploymentPeriod.start_date.desc()))
    if cur is not None:
        if cur.start_date == since:
            return cur
        if cur.start_date > since:
            cur.start_date = since          # период начался раньше — расширяем
            cur.note = note or cur.note
            db.flush()
            return cur
        cur.end_date = since - dt.timedelta(days=1)   # закрыли старый, открываем новый
        db.flush()
    period = EmploymentPeriod(employee_id=emp.id, start_date=since, end_date=None,
                              note=note, created_by=user_id, created_at=utcnow())
    db.add(period)
    db.flush()
    return period


def close_period(db: Session, emp: Employee, until: dt.date, note: str = "") -> None:
    """Увольнение: текущий период закрывается датой `until` (последний рабочий день включительно)."""
    cur = db.scalar(select(EmploymentPeriod).where(
        EmploymentPeriod.employee_id == emp.id,
        EmploymentPeriod.end_date.is_(None)).order_by(EmploymentPeriod.start_date.desc()))
    if cur is None:
        return
    if until < cur.start_date:
        db.delete(cur)
    else:
        cur.end_date = until
        if note:
            cur.note = note
    db.flush()


def last_day(periods: Iterable[EmploymentPeriod]) -> Optional[dt.date]:
    ends = [p.end_date for p in periods if p.end_date]
    return max(ends) if ends else None
