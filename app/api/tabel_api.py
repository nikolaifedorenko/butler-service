"""Табель: просмотр и редактирование кода дня и плановых часов (первичный документ, спец. 1.1)."""
from __future__ import annotations

import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import Principal, audit
from ..db import get_db
from ..engine.adapters.sql_closings import SqlSettlementStore
from ..engine.adapters.sql_settings import SqlSettingsAdapter
from ..engine.adapters.sql_timesheet import EMPTY_DAY_CODE
from ..engine.application.periods import month_period
from ..engine.domain.day_card.hours_text import hours_text
from ..engine.domain.types.errors import ConfigError
from ..models import Employee, TabelDay, utcnow
from ..permissions import principal_permissions, require_perm
from ..tabel_fill import fill_from_schedule
from .engine_common import domain_error_text, emp_brief, period_employees

router = APIRouter(prefix="/api/tabel", tags=["tabel"])


def _settings(db: Session, period):
    try:
        return SqlSettingsAdapter(db).load(period)
    except ConfigError as exc:
        raise HTTPException(status_code=409, detail=domain_error_text(exc))


def _lock_state(db: Session, emp_id: int, period) -> str:
    """open — можно править; last_closed — можно, но нужен пересчёт; locked — более ранний закрытый."""
    state = SqlSettlementStore(db).period_state(str(emp_id), period)
    if not state.closed:
        return "open"
    return "locked" if state.next_closed else "last_closed"


@router.get("")
def get_tabel(year: int, month: int, principal: Principal = Depends(require_perm("tabel.view")),
              db: Session = Depends(get_db)):
    period = month_period(year, month)
    st = _settings(db, period)
    emps = period_employees(db, period.start, period.end)
    rows = {(r.employee_id, r.date): r for r in db.scalars(select(TabelDay).where(
        TabelDay.employee_id.in_([e.id for e in emps]), TabelDay.date >= period.start,
        TabelDay.date <= period.end))} if emps else {}
    days = [period.start + dt.timedelta(days=i) for i in range((period.end - period.start).days + 1)]
    out = []
    for e in emps:
        cells, plan = {}, 0
        for d in days:
            r = rows.get((e.id, d))
            if r:
                cells[d.isoformat()] = {"code": r.code, "hours": r.plan_minutes / 60, "source": r.source,
                                        "note": r.note, "value": f"{r.code} {hours_text(r.plan_minutes)}"
                                        if st.day_codes.get(r.code) and st.day_codes[r.code].carries_hours else r.code}
                plan += r.plan_minutes
        out.append({"employee": emp_brief(e), "cells": cells, "plan_hours": plan / 60,
                    "lock": _lock_state(db, e.id, period)})
    perms = principal_permissions(db, principal)
    return {"year": year, "month": month, "days": [d.isoformat() for d in days],
            "codes": [{"code": p.code, "title": p.title, "carries_hours": p.carries_hours,
                       "accepts_ut": p.accepts_ut, "counts_in_ut": p.counts_in_ut}
                      for p in st.day_codes.values()],
            "values": sorted(st.windows.keys()), "empty_code": EMPTY_DAY_CODE,
            "can_edit": "tabel.edit" in perms, "rows": out}


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


def _apply_cell(db: Session, principal: Principal, emp_id: int, day: dt.date, code: str, hours: float,
                note: str, st) -> Optional[str]:
    period = month_period(day.year, day.month)
    lock = _lock_state(db, emp_id, period)
    if lock == "locked":
        raise HTTPException(status_code=409, detail=f"{day:%m.%Y}: период закрыт, и следующий уже закрыт — "
                                                     "править можно только последний закрытый период")
    code = code.strip()
    if code and code not in st.day_codes:
        raise HTTPException(status_code=422, detail=f"Код «{code}» отсутствует в справочнике Т1")
    minutes = int(round(hours * 60)) if code and st.day_codes[code].carries_hours else 0
    if code and st.day_codes[code].carries_hours and f"{code} {hours_text(minutes)}" not in st.windows:
        raise HTTPException(status_code=422, detail=f"Для «{code} {hours_text(minutes)}» нет окна в Т2 — "
                                                     "добавьте его в настройках движка")
    row = db.scalar(select(TabelDay).where(TabelDay.employee_id == emp_id, TabelDay.date == day))
    before = None if row is None else f"{row.code} {row.plan_minutes / 60:g}"
    if not code:
        if row is not None:
            db.delete(row)
    else:
        if row is None:
            row = TabelDay(employee_id=emp_id, date=day)
            db.add(row)
        row.code, row.plan_minutes, row.note, row.source = code, minutes, note[:255], "manual"
        row.updated_by, row.updated_at = principal.user.id, utcnow()
    audit(db, principal, "tabel_cell", f"employee:{emp_id}",
          {"date": day.isoformat(), "before": before, "after": f"{code} {minutes / 60:g}" if code else None})
    return "Период закрыт — после правки выполните пересчёт в управленческом табеле" if lock == "last_closed" else None


@router.put("/cell")
def put_cell(payload: CellIn, principal: Principal = Depends(require_perm("tabel.edit")),
             db: Session = Depends(get_db)):
    st = _settings(db, month_period(payload.date.year, payload.date.month))
    warn = _apply_cell(db, principal, payload.employee_id, payload.date, payload.code, payload.hours, payload.note, st)
    db.commit()
    return {"ok": True, "warning": warn}


@router.post("/bulk")
def bulk(payload: BulkIn, principal: Principal = Depends(require_perm("tabel.edit")), db: Session = Depends(get_db)):
    warns = set()
    for d in payload.dates:
        st = _settings(db, month_period(d.year, d.month))
        for eid in payload.employee_ids:
            w = _apply_cell(db, principal, eid, d, payload.code, payload.hours, "", st)
            if w:
                warns.add(w)
    db.commit()
    return {"ok": True, "cells": len(payload.dates) * len(payload.employee_ids), "warnings": sorted(warns)}


class FillIn(BaseModel):
    year: int
    month: int
    employee_ids: Optional[list[int]] = None
    overwrite: str = "empty"      # empty — только пустые; schedule — и заполненные из графика; all — все


@router.post("/fill-from-schedule")
def fill(payload: FillIn, principal: Principal = Depends(require_perm("tabel.edit")), db: Session = Depends(get_db)):
    period = month_period(payload.year, payload.month)
    st = _settings(db, period)
    emps = [e for e in period_employees(db, period.start, period.end, payload.employee_ids)
            if _lock_state(db, e.id, period) != "locked"]
    mode = {"empty": False, "schedule": True, "all": "all"}.get(payload.overwrite, False)
    res = fill_from_schedule(db, emps, period.start, period.end, st, mode, principal.user.id)
    audit(db, principal, "tabel_fill_from_schedule", f"{payload.year}-{payload.month:02d}",
          {"employees": [e.id for e in emps], "overwrite": payload.overwrite, **{k: res[k] for k in ("written", "skipped")}})
    db.commit()
    return res


def ensure_tabel_filled(db: Session, first: dt.date, last: dt.date) -> int:
    """Первичное заполнение Табеля из Графика для пустых ячеек (миграция и демо-данные)."""
    period = month_period(first.year, first.month)
    st = SqlSettingsAdapter(db).load(period)
    emps = list(db.scalars(select(Employee).where(Employee.deleted_at.is_(None))))
    res = fill_from_schedule(db, emps, first, last, st, False, None)
    return res["written"]
