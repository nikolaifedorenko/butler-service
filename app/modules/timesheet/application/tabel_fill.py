"""Заполнение Табеля из циклов графика (инструмент ввода — вне расчётного ядра, 1.3).

Решение владельца (11.10.2026): цикл-редактор сохраняется как инструмент заполнения
Табеля — первичного документа (3.3). График генерируется из Табеля по окнам
CFG-WINDOWS (16.3), а не наоборот.

Решение владельца (18.10.2026): значение рабочего дня принадлежит СОТРУДНИКУ, а не
словарю смен: карточка → «Перевод в блок» задаёт блок и код/значение рабочего дня
(BlockAssignment.pattern_json → "value"), связка «смена → код Табеля» (tzh_code)
удалена. Цикл отвечает только на вопрос «рабочий ли день» (base/week5/cycle,
Смена 2 — всегда противофаза), а код и плановые минуты берутся из ключа строки
CFG-WINDOWS значения сотрудника («Я 10,75» → код «Я», план 645 минут).

Правила:
* рабочий день по шаблону → значение сотрудника; окно значения не пересекает
  полночь (CHK-WINDOW-BOUNDS), поэтому значение ставится целиком в свой день,
  а присутствие после полуночи относится к карточке следующего дня (4.7,
  RUL-WORK-AND-OVERTIME);
* значение не задано, отсутствует в CFG-WINDOWS или код значения не несёт часов →
  предупреждение и день не заполняется: честнее предупредить, чем молча поставить
  ноль (паттерн EX-15);
* выходной по шаблону → код «В»;
* дни вне трудоустройства не заполняются (RUL-EMPLOYMENT-PERIOD: строк вне периода
  трудоустройства в Табеле быть не должно — CHK-DAYS-IN-PERIOD).
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import lock_employee
from app.core.time import utcnow
from app.modules.employees.application import Employee, periods_of

from ..adapters.orm import TabelDay
from ..adapters.sql_settings import SqlSettingsAdapter
from ..domain.settings.types import Settings
from .base_schedule import BlockIndex, load_base_config, pattern_for_date, working_flag
from .months import month_period

OFF_CODE = "В"


def value_for_day(db: Session, emp: Employee, day: dt.date, st: Settings,
                  periods: list, cfg=None, index=None, catalog=None) -> tuple[Optional[str], int, str]:
    """(код, плановые минуты, предупреждение) для дня; код None — день не заполняется
    (вне трудоустройства / ручной режим / значение непредставимо).

    `periods` — уже загруженные периоды работы сотрудника (оставлены для совместимости
    подписи: занятость проверяет цикл заполнения). `catalog` — исторический параметр
    словаря смен: в модели значения сотрудника не используется.
    """
    cfg = cfg or load_base_config(db)
    pat = pattern_for_date(db, emp, day, cfg, index=index)
    if pat.get("kind") == "manual":
        return None, 0, ""
    try:
        flag = working_flag(cfg, pat, day)
    except ValueError:
        return None, 0, (f"{day:%d.%m}: некорректный цикл в шаблоне блока — "
                         "исправьте цикл или опорную дату")
    if not flag:
        return OFF_CODE, 0, ""
    value = (pat.get("value") or "").strip()
    if not value:
        return None, 0, (f"{day:%d.%m}: не задано значение рабочего дня — выберите "
                         "код в карточке сотрудника («Перевод в блок»)")
    window = st.windows.get(value)
    if window is None:
        return None, 0, (f"{day:%d.%m}: значения «{value}» нет в CFG-WINDOWS — добавьте "
                         "значение в настройках или измените значение сотрудника "
                         "(паттерн EX-15)")
    code, _, hours = value.partition(" ")
    policy = st.day_code_policy.get(code)
    if policy is None or not policy.carries_hours:
        return None, 0, (f"{day:%d.%m}: код «{code}» значения «{value}» не несёт часов — "
                         "измените значение рабочего дня сотрудника")
    return code, int(round(float(hours.replace(",", ".")) * 60)), ""


def fill_timesheet_from_cycles(db: Session, employees: list[Employee], first: dt.date,
                               last: dt.date, st: Settings | None = None,
                               overwrite: bool = False,
                               actor_id: Optional[int] = None) -> dict:
    st = st or SqlSettingsAdapter(db).load(month_period(first.year, first.month))
    cfg = load_base_config(db)
    index = BlockIndex.load(db, [e.id for e in employees])
    periods = {e.id: periods_of(db, e.id) for e in employees}
    existing = {(r.employee_id, r.date): r for r in db.scalars(select(TabelDay).where(
        TabelDay.employee_id.in_([e.id for e in employees]), TabelDay.date >= first,
        TabelDay.date <= last))} if employees else {}
    written, skipped, warnings = 0, 0, []

    from app.modules.employees.application import employed_on
    # по возрастанию id — один порядок блокировок у всех массовых записей (без взаимных)
    for emp in sorted(employees, key=lambda e: e.id):
        lock_employee(db, emp.id)        # Табель — вход закрытия периода (TOCTOU)
        day = first
        while day <= last:
            if not employed_on(periods.get(emp.id, []), day):
                day += dt.timedelta(days=1)
                continue
            code, minutes, warn = value_for_day(db, emp, day, st, periods.get(emp.id, []),
                                                cfg, index)
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
