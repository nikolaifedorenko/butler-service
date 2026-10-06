"""Заполнение Табеля из Графика (вне расчётного ядра: спец. 4.7 — построение одного документа
из другого выполняется вне домена; домен получает уже готовые Табель и График).

Правило: плановые отрезки смен Графика раскладываются по календарным дням; значение Табеля
подбирается по окну Т2 с такими же отрезками («Я 12» = 08:00–20:00, «Н 4» = 20:00–24:00,
«Н 8» = 00:00–08:00, «Н 12» = 00:00–08:00 + 20:00–24:00). День без работы получает код
отсутствия из словаря смен (код Т-13), если он есть в Т1, иначе «В».
«Выходной за часы» и «Отпросился» (списание из банка) не убирают план: в Табель идёт смена
базового цикла, а отсутствие остаётся в Графике (недостача гасится каскадом, спец. Ф24).
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .base_schedule import base_shift
from .engine.adapters.sql_schedule import ScheduleCache
from .engine.domain.settings.types import Settings
from .models import Employee, TabelDay, utcnow
from .schedule_helpers import shift_window

OFF_CODE = "В"


def _segments(win_start: dt.datetime, win_end: dt.datetime, day: dt.date) -> list[tuple[int, int]]:
    lo = dt.datetime.combine(day, dt.time(0))
    a = max(win_start, lo)
    b = min(win_end, lo + dt.timedelta(days=1))
    if b <= a:
        return []
    return [(int((a - lo).total_seconds() // 60), int((b - lo).total_seconds() // 60))]


def _merge(segs):
    out = []
    for a, b in sorted(segs):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return tuple(out)


def _planned_shift(db: Session, cache: ScheduleCache, emp: Employee, day: dt.date):
    entry, shift = cache.day(emp, day)
    if shift is not None and shift.kind != "work" and getattr(shift, "deduct_from_bank", False):
        return base_shift(db, emp, day, cfg=cache.cfg, catalog=cache.catalog), shift
    return shift, shift


def value_for_day(db: Session, cache: ScheduleCache, emp: Employee, day: dt.date,
                  st: Settings) -> Optional[tuple[str, int, str]]:
    """(код, плановые минуты, предупреждение) для дня; None — сотрудник в этот день не работал."""
    segs = []
    own_shift = None
    for d in (day - dt.timedelta(days=1), day):
        planned, raw = _planned_shift(db, cache, emp, d)
        if d == day:
            own_shift = raw
        ws, we = shift_window(planned, d)
        if ws and we:
            segs += _segments(ws, we, day)
    segs = _merge(segs)
    if not segs:
        if own_shift is None:
            return None
        code = (getattr(own_shift, "tzh_code", "") or "").strip()
        return (code if code in st.day_codes and not st.day_codes[code].carries_hours else OFF_CODE), 0, ""
    minutes = sum(b - a for a, b in segs)
    match = next((w for w in st.windows.values() if tuple(w.segments) == segs), None)
    if match:
        return match.code, match.plan_minutes, ""
    same = next((w for w in st.windows.values() if w.plan_minutes == minutes), None)
    code = same.code if same else "Я"
    span = ", ".join(f"{a // 60:02d}:{a % 60:02d}–{b // 60:02d}:{b % 60:02d}" for a, b in segs)
    return code, minutes, f"{day:%d.%m}: смена {span} не совпадает ни с одним окном Т2 — проставлено «{code} {minutes / 60:g}»"


def fill_from_schedule(db: Session, employees: list[Employee], first: dt.date, last: dt.date, st: Settings,
                       overwrite: bool, actor_id: Optional[int]) -> dict:
    cache = ScheduleCache(db)
    cache.preload([e.id for e in employees], first - dt.timedelta(days=1), last)
    existing = {(r.employee_id, r.date): r for r in db.scalars(select(TabelDay).where(
        TabelDay.employee_id.in_([e.id for e in employees]), TabelDay.date >= first, TabelDay.date <= last))}
    written, skipped, warnings = 0, 0, []
    for emp in employees:
        d = first
        while d <= last:
            value = value_for_day(db, cache, emp, d, st)
            row = existing.get((emp.id, d))
            if value is not None and (row is None or (overwrite and row.source != "manual") or overwrite == "all"):
                code, minutes, warn = value
                if row is None:
                    row = TabelDay(employee_id=emp.id, date=d)
                    db.add(row)
                row.code, row.plan_minutes, row.source = code, minutes, "schedule"
                row.updated_by, row.updated_at = actor_id, utcnow()
                written += 1
                if warn:
                    warnings.append(f"{emp.display_name} {warn}")
            elif value is not None:
                skipped += 1
            d += dt.timedelta(days=1)
    db.flush()
    return {"written": written, "skipped": skipped, "warnings": warnings}
