"""Вкладка «Табель» (16.5): первичный документ — код дня и информационный план строки.

Запись валидируется ТЕМИ ЖЕ доменными проверочными функциями через application
(save_timesheet_day, v7.1/F-16): код существует в CFG-DAY-CODES; carries_hours = Да ⇒
план задан, > 0 и кратен 15; carries_hours = Нет ⇒ часы запрещены; для значения с часами
есть строка CFG-WINDOWS. Редактируемость: незакрытый период — свободно; последний
закрытый — с предупреждением «изменения попадут в результат только через пересчёт»;
более ранние закрытые — только чтение. После сохранения дня D — перегенерация Графика
дня D (16.3). Пересчёт часов не запускается (16.1 п.2).

Циклы графика — инструмент заполнения Табеля (решение владельца 11.10.2026)."""
from __future__ import annotations

import datetime as dt
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import principal_permissions, require_perm
from app.core.time import local_date
from app.modules.employees.application import Employee

from ..adapters.orm import TabelDay
from ..adapters.sql_settings import SqlSettingsAdapter, base_version
from ..application import timesheet_edit
from ..application.engine_common import (
    day_code_colors,
    day_code_rows,
    emp_brief,
    engine_ports,
    now_utc,
    period_employees,
)
from ..application.months import half_month_period, month_period
from ..application.schedule_view import rebuild_generated_for_days, rebuild_generated_schedule
from ..application.tabel_fill import fill_timesheet_from_cycles
from ..domain.types.entities import Period
from .formatting import fmt_hours_strict, hm
from .period_params import ensure_period

router = APIRouter(prefix="/api/tabel", tags=["tabel"])


def _settings(db: Session, period: Period):
    # ConfigError → 422 с текстом нарушений — централизованный хэндлер main.py (§5.3)
    return SqlSettingsAdapter(db).load(period)


def _granularity(db: Session, period: Period) -> str:
    return _settings(db, period).period_granularity


def _code_titles(db: Session) -> dict[str, str]:
    """Человеческие подписи кодов CFG-DAY-CODES — данные приложения в payload версии
    (домен Settings их не знает, 8.4: тексты — слой interface/приложение)."""
    version = base_version(db, local_date())
    payload = json.loads(version.payload_json) if version else {}
    return {code: row.get("title", "") for code, row in payload.get("day_code_policy", {}).items()}


def _code_colors(db: Session) -> dict[str, str]:
    """Цвета кодов Табеля (presentation версии справочников) — общий сервис:
    тот же источник использует График для цветов ячеек (16.10.2026)."""
    return day_code_colors(db)


@router.get("")
def get_tabel(year: int, month: int, half: Optional[int] = None,
              principal: Principal = Depends(require_perm("tabel.view")),
              db: Session = Depends(get_db)):
    ensure_period(year, month)
    granularity = _granularity(db, month_period(year, month))
    period = _period_of(db, year, month, half)
    st = _settings(db, period)
    emps = period_employees(db, period.start, period.end)
    rows = {(r.employee_id, r.date): r for r in db.scalars(select(TabelDay).where(
        TabelDay.employee_id.in_([e.id for e in emps]), TabelDay.date >= period.start,
        TabelDay.date <= period.end))} if emps else {}
    days = [period.start + dt.timedelta(days=i)
            for i in range((period.end - period.start).days + 1)]
    titles = _code_titles(db)

    code_rows = day_code_rows(db)
    p = ports(db, principal)
    locks = timesheet_edit.lock_states([str(e.id) for e in emps], period.start, p)
    out = []
    for e in emps:
        cells, plan, missing = {}, 0, []
        for d in days:
            r = rows.get((e.id, d))
            if r:
                policy = st.day_code_policy.get(r.code)
                value = (f"{r.code} {fmt_hours_strict(r.plan_minutes, e.id, d)}"
                         if policy and policy.carries_hours else r.code)
                cells[d.isoformat()] = {"code": r.code, "hours": r.plan_minutes / 60,
                                        "source": r.source, "note": r.note, "value": value}
                plan += r.plan_minutes
            else:
                missing.append(d.isoformat())
        out.append({"employee": emp_brief(e), "cells": cells, "plan_hours": plan / 60,
                    "missing_days": missing, "lock": locks[str(e.id)]})
    perms = principal_permissions(db, principal)
    return {"year": year, "month": month, "half": half, "granularity": granularity,
            "period": {"start": period.start.isoformat(), "end": period.end.isoformat()},
            "days": [d.isoformat() for d in days],
            "colors": _code_colors(db),
            "codes": [{"code": code, "title": titles.get(code, ""),
                       "carries_hours": p.carries_hours, "accepts_ut": p.accepts_ut,
                       "counts_in_ut": p.counts_in_ut, "plan_equals_fact_auto": p.plan_equals_fact_auto,
                       # шаблон заявления кода (18.10.2026): слой 0 печатает по коду,
                       # словарь смен в заявлениях больше не участвует
                       "doc_type": (code_rows.get(code) or {}).get("doc_type") or ""}
                      for code, p in st.day_code_policy.items()],
            "values": sorted(st.windows.keys()),
            # границы окон по значениям («Я 12» → 08:00–20:00): подсказки плашек
            # в редакторе ячейки — редактор собирает значения только из справочников
            "windows": {v: [hm(w.start_minute), hm(w.end_minute)]
                        for v, w in st.windows.items()},
            "can_edit": "tabel.edit" in perms, "rows": out}


def ports(db: Session, principal: Optional[Principal]):
    return engine_ports(db, principal, now_utc())


class CellIn(BaseModel):
    employee_id: int
    date: dt.date
    code: str = ""             # "" — очистить ячейку
    hours: float = 0
    note: str = ""


class BulkIn(BaseModel):
    employee_ids: list[int]
    dates: list[dt.date]
    code: str = ""
    hours: float = 0
    note: str = ""          # как у ячейки: непустое — в каждую ячейку, пустое — не трогает


def _apply_cell(db: Session, principal: Principal, emp_id: int, day: dt.date, code: str,
                hours: float, note: str, *, rebuild: bool = True) -> Optional[str]:
    """Запись одной ячейки Табеля (+ заметка, аудит, предупреждения).

    `rebuild=False` — массовый режим (P0-3 ревью 20.10.2026): График перегенерирует
    вызывающий код один раз на затронутый месяц, поэтому `manual_shifts_dropped`
    здесь пуст, а удалённые ручные смены собирает пакетная перегенерация.
    """
    p = ports(db, principal)
    minutes = int(round(hours * 60)) if code else None
    try:
        outcome = timesheet_edit.save_timesheet_day(str(emp_id), day, code.strip(), minutes, p,
                                                    rebuild=rebuild)
    except ValueError as exc:
        # ApplicationError → 409 и DomainError → 422 маппят центральные хэндлеры
        # (main.py, §5.3); ValueError — ошибка разбора входных значений (R2).
        raise HTTPException(status_code=422, detail=str(exc))
    row = db.scalar(select(TabelDay).where(TabelDay.employee_id == emp_id, TabelDay.date == day))
    if row is not None and note:
        row.note = note[:255]
    audit(db, principal, "tabel_cell", f"employee:{emp_id}",
          {"date": day.isoformat(), "after": f"{code} {hours:g}" if code else None,
           "manual_dropped": [d_.isoformat() for d_ in outcome.manual_shifts_dropped]})
    warning = None
    if outcome.needs_recalculate:
        warning = "Период закрыт — изменения попадут в результат только через пересчёт"
    if outcome.manual_shifts_dropped:
        warning = (warning + "; " if warning else "") + \
            "Ручные смены удалены: код дня больше не принимает коды УТ"
    return warning


@router.put("/cell")
def put_cell(payload: CellIn, principal: Principal = Depends(require_perm("tabel.edit")),
             db: Session = Depends(get_db)):
    warning = _apply_cell(db, principal, payload.employee_id, payload.date, payload.code,
                          payload.hours, payload.note)
    db.commit()
    return {"ok": True, "warning": warning}


@router.post("/bulk")
def bulk(payload: BulkIn, principal: Principal = Depends(require_perm("tabel.edit")),
         db: Session = Depends(get_db)):
    if len(payload.employee_ids) > 500 or len(payload.dates) > 366:
        raise HTTPException(status_code=422,
                            detail="Слишком большой запрос (максимум 500 сотрудников и 366 дат)")
    warns, errors = set(), []
    # записанные дни по сотрудникам: График перегенерируется ОДИН раз на затронутый
    # месяц после всей массовки, а не на каждую ячейку (P0-3 ревью 20.10.2026 —
    # 500×366 ячеек иначе делали сотни тысяч DELETE+INSERT generated-строк)
    touched: dict[int, list[dt.date]] = {}
    for d in payload.dates:
        for eid in payload.employee_ids:
            try:
                w = _apply_cell(db, principal, eid, d, payload.code, payload.hours,
                                payload.note, rebuild=False)
                if w:
                    warns.add(w)
                touched.setdefault(eid, []).append(d)
            except HTTPException as exc:
                errors.append({"employee_id": eid, "date": d.isoformat(), "detail": exc.detail})
    for eid, days in touched.items():
        outcome = rebuild_generated_for_days(str(eid), days, ports(db, principal))
        if outcome.manual_dropped:
            warns.add("Ручные смены удалены: код дня больше не принимает коды УТ")
    db.commit()
    return {"ok": not errors, "cells": len(payload.dates) * len(payload.employee_ids),
            "warnings": sorted(warns), "errors": errors}


class FillIn(BaseModel):
    year: int
    month: int
    employee_ids: Optional[list[int]] = None
    overwrite: bool = False      # True — перезаписывать немарочные ячейки


@router.post("/fill-from-cycles")
def fill(payload: FillIn, principal: Principal = Depends(require_perm("tabel.edit")),
         db: Session = Depends(get_db)):
    """Циклы графика заполняют Табель (инструмент ввода, решение владельца); График
    перегенерируется из Табеля (16.3). Закрытые периоды не трогаются (16.5)."""
    ensure_period(payload.year, payload.month)
    period = month_period(payload.year, payload.month)
    st = _settings(db, period)
    p = ports(db, principal)
    found = period_employees(db, period.start, period.end, payload.employee_ids)
    locks = timesheet_edit.lock_states([str(e.id) for e in found], period.start, p)
    emps = [e for e in found if locks[str(e.id)] != "locked"]
    res = fill_timesheet_from_cycles(db, emps, period.start, period.end, st,
                                     payload.overwrite, principal.user.id)
    for e in emps:
        rebuild_generated_schedule(str(e.id), period, p)
    audit(db, principal, "tabel_fill_from_cycles", f"{payload.year}-{payload.month:02d}",
          {"employees": len(emps), "overwrite": payload.overwrite,
           **{k: res[k] for k in ("written", "skipped")}})
    db.commit()
    return res


def _period_of(db: Session, year: int, month: int, half: Optional[int]) -> Period:
    """Период экрана: месяц либо половина месяца (настройка period_granularity, v7.1/R36)."""
    if _granularity(db, month_period(year, month)) == "half_month" and half:
        return half_month_period(year, month, 2 if half == 2 else 1)
    return month_period(year, month)


def _uncovered(db: Session, emps: list[Employee], period: Period) -> list[dict]:
    """Дни трудоустройства периода без строки Табеля.

    Табель обязан покрывать период (RUL-TIMESHEET-COVERS-PERIOD): пока есть пропуски,
    расчёт УТ не запустится. Список возвращается интерфейсу, чтобы «Сбросить» не
    выглядел «успешным», оставив дыры.
    """
    from app.modules.employees.application import employed_on, periods_of

    if not emps:
        return []
    rows = db.execute(select(TabelDay.employee_id, TabelDay.date).where(
        TabelDay.employee_id.in_([e.id for e in emps]), TabelDay.date >= period.start,
        TabelDay.date <= period.end)).all()
    have = {(eid, day) for eid, day in rows}
    out: list[dict] = []
    for e in emps:
        emp_periods = periods_of(db, e.id)
        day = period.start
        while day <= period.end:
            if employed_on(emp_periods, day) and (e.id, day) not in have:
                out.append({"employee_id": e.id, "employee": e.display_name,
                            "date": day.isoformat()})
            day += dt.timedelta(days=1)
    return out


class ResetIn(BaseModel):
    year: int
    month: int
    half: Optional[int] = None
    employee_ids: Optional[list[int]] = None   # пусто — весь период по всем сотрудникам


@router.post("/reset")
def reset(payload: ResetIn, principal: Principal = Depends(require_perm("tabel.edit")),
          db: Session = Depends(get_db)):
    """«Сбросить» (T3, решение владельца Q5 от 12.10.2026): убрать РУЧНЫЕ коды периода
    и вернуть автозаполнение Табеля из циклов.

    Табель — первичный документ: он заполняется из настроек сотрудника (циклов блоков),
    а ручная правка ячейки помечается `source="manual"` и автозаполнением больше не
    перезаписывается. «Сбросить» удаляет именно ручные строки периода и заново запускает
    заполнение из циклов, после чего График перегенерируется из Табеля (16.3).

    Границы — как у «Заполнить из циклов»:
    * закрытые периоды не трогаются: сотрудник с `lock_state == "locked"` пропускается
      и возвращается в `locked_skipped` (RUL-CLOSED-PERIOD-IMMUTABLE);
    * дни вне трудоустройства не заполняются (RUL-EMPLOYMENT-PERIOD);
    * если после сброса день остался пустым (цикл не даёт значения: нет строки
      CFG-WINDOWS либо отрезки дня одним значением непредставимы), день возвращается
      в `uncovered` — ячейку нужно заполнить вручную, иначе расчёт не запустится.

    Пересчёт часов не запускается (16.1 п.2): итоги периода обновятся при чтении УТ.
    """
    ensure_period(payload.year, payload.month)
    period = _period_of(db, payload.year, payload.month, payload.half)
    st = _settings(db, period)
    p = ports(db, principal)
    emps: list[Employee] = []
    locked: list[int] = []
    found = period_employees(db, period.start, period.end, payload.employee_ids)
    locks = timesheet_edit.lock_states([str(e.id) for e in found], period.start, p)
    for e in found:
        if locks[str(e.id)] == "locked":
            locked.append(e.id)
        else:
            emps.append(e)
    ids = [e.id for e in emps]
    manual: list[TabelDay] = list(db.scalars(select(TabelDay).where(
        TabelDay.employee_id.in_(ids), TabelDay.date >= period.start,
        TabelDay.date <= period.end, TabelDay.source == "manual"))) if ids else []
    cleared = [{"employee_id": r.employee_id, "date": r.date.isoformat(), "code": r.code,
                "hours": round(r.plan_minutes / 60, 2), "note": r.note or ""} for r in manual]
    for r in manual:
        db.delete(r)
    db.flush()                                     # заполнение не должно видеть ручные строки
    res = fill_timesheet_from_cycles(db, emps, period.start, period.end, st, False,
                                     principal.user.id)
    dropped: list[str] = []
    for e in emps:
        outcome = rebuild_generated_schedule(str(e.id), period, p)
        dropped += [f"{e.display_name} {d:%d.%m}" for d in outcome.manual_dropped]
    uncovered = _uncovered(db, emps, period)
    audit(db, principal, "tabel_reset",
          f"{payload.year}-{payload.month:02d}" + (f"-h{payload.half}" if payload.half else ""),
          {"employees": len(emps), "cleared": len(cleared), "written": res["written"],
           "locked_skipped": locked, "uncovered": len(uncovered),
           "manual_shifts_dropped": dropped})
    db.commit()
    return {"ok": True, "cleared": len(cleared), "cells": cleared[:80],
            "written": res["written"], "skipped": res["skipped"],
            "warnings": res["warnings"], "uncovered": uncovered[:80],
            "uncovered_total": len(uncovered), "locked_skipped": locked,
            "manual_shifts_dropped": dropped}


def ensure_tabel_filled(db: Session, first: dt.date, last: dt.date) -> int:
    """Первичное заполнение Табеля из циклов (миграция и демо-данные)."""
    period = month_period(first.year, first.month)
    st = SqlSettingsAdapter(db).load(period)
    emps = list(db.scalars(select(Employee).where(Employee.deleted_at.is_(None))))
    res = fill_timesheet_from_cycles(db, emps, first, last, st, False, None)
    return res["written"]
