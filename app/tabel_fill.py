"""Заполнение Табеля из циклов графика (инструмент ввода — вне расчётного ядра, 1.3).

Решение владельца (11.10.2026): цикл-редактор сохраняется как инструмент заполнения
Табеля — первичного документа (3.3). График генерируется из Табеля по окнам
CFG-WINDOWS (16.3), а не наоборот.

Правила:
* **смена через полночь оформляется ОДНИМ значением в дне-якоре** (норматив от
  12.10.2026): суточная/ночная смена не дробится на два значения двух дней. В Табеле
  стоит обычная явка, окно которой начинается вместе со сменой (суточные 08:00–08:00 →
  окно 08:00–20:00). Присутствие режется локальными полуночами, поэтому работа после
  полуночи попадает в карточку следующего дня: рабочее время = присутствие ∩ окно
  своего дня, всё вне окна — переработка (4.7, RUL-WORK-AND-OVERTIME). «Утро» такой
  смены в следующий день не переносится — день считается самостоятельно;
* дневные части смен, накрывающие день (своя смена + «утро» ночной смены предыдущего
  дня, если у той нет явной нормы), сливаются; если получился один отрезок — значение
  Табеля ищется по точным границам окон CFG-WINDOWS (код и план — из ключа окна);
* день без рабочих частей → код отсутствия из словаря (если есть в CFG-DAY-CODES и не
  несёт часов), иначе «В»;
* несколько несмежных отрезков в дне одним значением непредставимы (окно не пересекает
  полночь, CHK-WINDOW-BOUNDS) — предупреждение: нужен другой цикл или ручная ячейка;
* дни вне трудоустройства не заполняются (RUL-EMPLOYMENT-PERIOD: строк вне периода
  трудоустройства в Табеле быть не должно — CHK-DAYS-IN-PERIOD).
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .base_schedule import BlockIndex, base_shift, load_base_config
from .employment import employed_on, periods_of
from .engine.adapters.sql_settings import SqlSettingsAdapter
from .engine.application.months import month_period
from .engine.domain.settings.types import Settings
from .models import Employee, ShiftType, TabelDay, utcnow
from .shiftrev import ShiftCatalog

OFF_CODE = "В"

Segment = tuple[int, int]


def _hm_minutes(hhmm: str) -> int:
    h, m = (int(x) for x in hhmm.split(":"))
    return h * 60 + m


def _shift_day_parts(shift: Optional[ShiftType], day: dt.date,
                     anchor: dt.date) -> list[Segment]:
    """Части смены в пределах дня day; anchor — день начала смены."""
    if shift is None or shift.kind != "work" or not shift.start_time or not shift.end_time:
        return []
    start, end = _hm_minutes(shift.start_time), _hm_minutes(shift.end_time)
    if shift.overnight or end <= start:
        end += 1440                                   # смена через полночь (сутки 08→08 = 24 ч)
    if end <= 1440:
        return [(start, end)] if anchor == day else []
    if anchor == day:
        return [(start, 1440)]
    if anchor == day - dt.timedelta(days=1):
        return [(0, end - 1440)]
    return []


def _merge(segs: list[Segment]) -> list[Segment]:
    out: list[Segment] = []
    for a, b in sorted(segs):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _find_value(st: Settings, segment: Segment) -> Optional[str]:
    for key, w in st.windows.items():
        if (w.start_minute, w.end_minute) == segment:
            return key
    return None


def _is_overnight(shift) -> bool:
    """Смена пересекает полночь (сутки 08:00–08:00, ночная 20:00–08:00)."""
    if shift is None or getattr(shift, "kind", "") != "work":
        return False
    start, end = shift.start_time or "", shift.end_time or ""
    if not start or not end:
        return False
    return bool(getattr(shift, "overnight", False)) or _hm_minutes(end) <= _hm_minutes(start)


def _anchor_value(st: Settings, shift, day: dt.date) -> tuple[Optional[str], int, str]:
    """Значение Табеля для смены через полночь — целиком в дне-якоре.

    Окно такой смены — стандартное рабочее окно, начинающееся вместе со сменой
    (суточные 08:00–08:00 → окно 08:00–20:00): по нему считаются рабочее время,
    недостача и план карточки, а часы вне окна расчёт относит к переработке дня.
    Часов в смене через полночь больше, чем в окне, поэтому значение ищется по
    **началу** окна, а не по его границам целиком.

    Если одному началу соответствует несколько значений справочника (например «Я 12»
    и «Я 10,75» при окне 08:00–20:00 — часы значения меньше длины окна), берётся первое
    по порядку в справочнике окон: расчёт от этого не меняется, у обоих значений окно
    одно. Точное значение при необходимости ставится в ячейку вручную — ручные строки
    Табеля заполнение из циклов не перезаписывает.

    Без подходящей строки CFG-WINDOWS значение не возвращается: расчёт остановился бы
    на CHK-WINDOW-EXISTS, поэтому честнее предупредить при заполнении.
    """
    code = ((getattr(shift, "tzh_code", "") or "").strip())
    policy = st.day_code_policy.get(code)
    if policy is None or not policy.carries_hours:
        return None, 0, (f"{day:%d.%m}: у смены через полночь не задан код Табеля, "
                         "несущий часы, — укажите его в словаре смен")
    start = _hm_minutes(shift.start_time)
    candidates = [key for key, w in st.windows.items() if w.start_minute == start]
    if not candidates:
        return None, 0, (f"{day:%d.%m}: для смены через полночь нет строки CFG-WINDOWS "
                         f"с началом {shift.start_time} — добавьте значение в настройках "
                         "(паттерн EX-15)")
    value = candidates[0]
    hours = value.partition(" ")[2]
    return code, int(round(float(hours.replace(",", ".")) * 60)), ""


def _off_code(st: Settings, shift: Optional[ShiftType]) -> str:
    code = ((getattr(shift, "tzh_code", "") or "").strip() if shift is not None else "")
    policy = st.day_code_policy.get(code)
    if policy is not None and not policy.carries_hours:
        return code
    return OFF_CODE


def value_for_day(db: Session, emp: Employee, day: dt.date, st: Settings,
                  cfg=None, index=None, catalog=None) -> tuple[Optional[str], int, str]:
    """(код, плановые минуты, предупреждение) для дня; код None — день не заполняется
    (вне трудоустройства / ручной режим / значение непредставимо)."""
    today_shift = base_shift(db, emp, day, cfg=cfg, index=index, catalog=catalog)
    if _is_overnight(today_shift):
        # смена через полночь: одно значение в дне-якоре, «утро» следующего дня не учитываем
        return _anchor_value(st, today_shift, day)
    yesterday_shift = base_shift(db, emp, day - dt.timedelta(days=1), cfg=cfg, index=index,
                                 catalog=catalog)
    tail = [] if _is_overnight(yesterday_shift) else \
        _shift_day_parts(yesterday_shift, day, day - dt.timedelta(days=1))
    parts = _merge(_shift_day_parts(today_shift, day, day) + tail)
    if not parts:
        return _off_code(st, today_shift), 0, ""
    if len(parts) > 1:
        span = ", ".join(f"{a // 60:02d}:{a % 60:02d}–{b // 60:02d}:{b % 60:02d}" for a, b in parts)
        return None, 0, (f"{day:%d.%m}: отрезки {span} одним значением Табеля непредставимы "
                         "(окно не пересекает полночь) — измените цикл или заполните ячейку вручную")
    value = _find_value(st, parts[0])
    if value is None:
        a, b = parts[0]
        return None, 0, (f"{day:%d.%m}: для окна {a // 60:02d}:{a % 60:02d}–{b // 60:02d}:"
                         f"{b % 60:02d} нет строки CFG-WINDOWS — добавьте значение в настройках "
                         "(паттерн EX-15)")
    code, _, hours = value.partition(" ")
    return code, int(round(float(hours.replace(",", ".")) * 60)), ""


def fill_timesheet_from_cycles(db: Session, employees: list[Employee], first: dt.date,
                               last: dt.date, st: Settings | None = None,
                               overwrite: bool = False,
                               actor_id: Optional[int] = None) -> dict:
    st = st or SqlSettingsAdapter(db).load(month_period(first.year, first.month))
    cfg = load_base_config(db)
    catalog = ShiftCatalog.load(db)
    index = BlockIndex.load(db, [e.id for e in employees])
    periods = {e.id: periods_of(db, e.id) for e in employees}
    existing = {(r.employee_id, r.date): r for r in db.scalars(select(TabelDay).where(
        TabelDay.employee_id.in_([e.id for e in employees]), TabelDay.date >= first,
        TabelDay.date <= last))} if employees else {}
    written, skipped, warnings = 0, 0, []

    for emp in employees:
        day = first
        while day <= last:
            if not employed_on(periods.get(emp.id, []), day):
                day += dt.timedelta(days=1)
                continue
            code, minutes, warn = value_for_day(db, emp, day, st, cfg, index, catalog)
            if warn:
                warnings.append(f"{emp.display_name} {warn}")
            row = existing.get((emp.id, day))
            if code is not None and (row is None or overwrite or row.source != "manual"):
                if row is None:
                    row = TabelDay(employee_id=emp.id, date=day)
                    db.add(row)
                    existing[(emp.id, day)] = row
                row.code, row.plan_minutes, row.source = code, minutes, "cycle"
                row.updated_by, row.updated_at = actor_id, utcnow()
                written += 1
            elif code is not None:
                skipped += 1
            day += dt.timedelta(days=1)
    db.flush()
    return {"written": written, "skipped": skipped, "warnings": warnings}
