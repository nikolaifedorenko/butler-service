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

from ..auth import Principal, audit
from ..db import get_db
from ..engine.adapters.sql_settings import SqlSettingsAdapter, base_version
from ..engine.application import timesheet_edit
from ..engine.application.errors import ApplicationError
from ..engine.application.months import half_month_period, month_period
from ..engine.application.schedule_view import rebuild_generated_schedule
from ..engine.domain.day_card.fmt_hours import fmt_hours
from ..engine.domain.types.entities import Period
from ..engine.domain.types.errors import ConfigError, DomainError
from ..models import Employee, TabelDay
from ..permissions import principal_permissions, require_perm
from ..tabel_fill import fill_timesheet_from_cycles
from .engine_common import domain_error_text, emp_brief, engine_ports, now_utc, period_employees

router = APIRouter(prefix="/api/tabel", tags=["tabel"])


def _settings(db: Session, period: Period):
    try:
        return SqlSettingsAdapter(db).load(period)
    except ConfigError as exc:
        raise HTTPException(status_code=409, detail=domain_error_text(exc))


def _granularity(db: Session, period: Period) -> str:
    return _settings(db, period).period_granularity


def _code_titles(db: Session) -> dict[str, str]:
    """Человеческие подписи кодов CFG-DAY-CODES — данные приложения в payload версии
    (домен Settings их не знает, 8.4: тексты — слой interface/приложение)."""
    version = base_version(db, dt.date.today())
    payload = json.loads(version.payload_json) if version else {}
    return {code: row.get("title", "") for code, row in payload.get("day_code_policy", {}).items()}


@router.get("")
def get_tabel(year: int, month: int, half: Optional[int] = None,
              principal: Principal = Depends(require_perm("tabel.view")),
              db: Session = Depends(get_db)):
    granularity = _granularity(db, month_period(year, month))
    period = (half_month_period(year, month, 2 if half == 2 else 1)
              if granularity == "half_month" and half else month_period(year, month))
    st = _settings(db, period)
    emps = period_employees(db, period.start, period.end)
    rows = {(r.employee_id, r.date): r for r in db.scalars(select(TabelDay).where(
        TabelDay.employee_id.in_([e.id for e in emps]), TabelDay.date >= period.start,
        TabelDay.date <= period.end))} if emps else {}
    days = [period.start + dt.timedelta(days=i)
            for i in range((period.end - period.start).days + 1)]
    titles = _code_titles(db)
    p = ports(db, principal)
    out = []
    for e in emps:
        cells, plan, missing = {}, 0, []
        for d in days:
            r = rows.get((e.id, d))
            if r:
                policy = st.day_code_policy.get(r.code)
                value = (f"{r.code} {fmt_hours(r.plan_minutes)}"
                         if policy and policy.carries_hours else r.code)
                cells[d.isoformat()] = {"code": r.code, "hours": r.plan_minutes / 60,
                                        "source": r.source, "note": r.note, "value": value}
                plan += r.plan_minutes
            else:
                missing.append(d.isoformat())
        lock = timesheet_edit.lock_state(str(e.id), period.start, p)
        out.append({"employee": emp_brief(e), "cells": cells, "plan_hours": plan / 60,
                    "missing_days": missing, "lock": lock})
    perms = principal_permissions(db, principal)
    return {"year": year, "month": month, "half": half, "granularity": granularity,
            "period": {"start": period.start.isoformat(), "end": period.end.isoformat()},
            "days": [d.isoformat() for d in days],
            "codes": [{"code": code, "title": titles.get(code, ""),
                       "carries_hours": p.carries_hours, "accepts_ut": p.accepts_ut,
                       "counts_in_ut": p.counts_in_ut, "plan_equals_fact_auto": p.plan_equals_fact_auto}
                      for code, p in st.day_code_policy.items()],
            "values": sorted(st.windows.keys()),
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


def _apply_cell(db: Session, principal: Principal, emp_id: int, day: dt.date, code: str,
                hours: float, note: str) -> Optional[str]:
    p = ports(db, principal)
    minutes = int(round(hours * 60)) if code else None
    try:
        outcome = timesheet_edit.save_timesheet_day(str(emp_id), day, code.strip(), minutes, p)
    except ApplicationError as exc:
        raise HTTPException(status_code=409, detail=domain_error_text(exc))
    except (DomainError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=domain_error_text(exc))
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
    warns, errors = set(), []
    for d in payload.dates:
        for eid in payload.employee_ids:
            try:
                w = _apply_cell(db, principal, eid, d, payload.code, payload.hours, "")
                if w:
                    warns.add(w)
            except HTTPException as exc:
                errors.append({"employee_id": eid, "date": d.isoformat(), "detail": exc.detail})
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
    period = month_period(payload.year, payload.month)
    st = _settings(db, period)
    p = ports(db, principal)
    emps = [e for e in period_employees(db, period.start, period.end, payload.employee_ids)
            if timesheet_edit.lock_state(str(e.id), period.start, p) != "locked"]
    res = fill_timesheet_from_cycles(db, emps, period.start, period.end, st,
                                     payload.overwrite, principal.user.id)
    for e in emps:
        rebuild_generated_schedule(str(e.id), period, p)
    audit(db, principal, "tabel_fill_from_cycles", f"{payload.year}-{payload.month:02d}",
          {"employees": len(emps), "overwrite": payload.overwrite,
           **{k: res[k] for k in ("written", "skipped")}})
    db.commit()
    return res


def ensure_tabel_filled(db: Session, first: dt.date, last: dt.date) -> int:
    """Первичное заполнение Табеля из циклов (миграция и демо-данные)."""
    period = month_period(first.year, first.month)
    st = SqlSettingsAdapter(db).load(period)
    emps = list(db.scalars(select(Employee).where(Employee.deleted_at.is_(None))))
    res = fill_timesheet_from_cycles(db, emps, first, last, st, False, None)
    return res["written"]
