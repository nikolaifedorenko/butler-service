"""API покрытия батлерами (§4.2, §4.5, §5): шаблоны, правка по дням, подбор и подмена,
«добавить смену в График». Изменяющие маршруты — с предпросмотром (§4.6)."""
from __future__ import annotations

import datetime as dt
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import principal_permissions, require_perm

from ..adapters.duty_timesheet import TimesheetDuty
from ..adapters.orm import CoverageLine
from ..application import coverage
from ..application.coverage import Scope
from ..application.fund import FundError
from ._ops import PREVIEW, err, run

router = APIRouter(prefix="/api/stays/coverage", tags=["stays"])
ASSIGN = require_perm("stays.assign")
MAX_DAYS = 62


class ScopeIn(BaseModel):
    reservation_id: Optional[int] = None
    group_id: Optional[int] = None
    guest_ids: list[int] = []

    def scope(self) -> Scope:
        return Scope(self.reservation_id, self.group_id, frozenset(self.guest_ids))


class TemplateIn(ScopeIn):
    kind: Literal["pair", "single"]
    butlers: list[int]
    first: dt.date
    last: dt.date
    replace: bool = False


class DayIn(ScopeIn):
    day: dt.date
    employee_id: Optional[int] = None          # пусто — снять назначение дня
    overnight: bool = False
    comment: str = Field("", max_length=255)


class DayChoice(BaseModel):
    day: dt.date
    employee_id: Optional[int] = None


class DaysIn(ScopeIn):
    days: list[DayChoice] = Field(min_length=1, max_length=MAX_DAYS)


class AddShiftIn(BaseModel):
    employee_id: int
    day: dt.date
    shift_type_id: int


def _span(first: dt.date, last: dt.date) -> None:
    if last < first or (last - first).days + 1 > MAX_DAYS:
        raise HTTPException(status_code=422, detail=f"Период — не больше {MAX_DAYS} дней")


@router.post("/template")
def template(payload: TemplateIn, preview_flag: bool = PREVIEW, principal: Principal = Depends(ASSIGN),
             db: Session = Depends(get_db)):
    _span(payload.first, payload.last)

    def op():
        plan = coverage.apply_template(db, payload.scope(), payload.kind, payload.butlers, payload.first,
                                       payload.last, payload.replace, TimesheetDuty(db))
        audit(db, principal, "stays_coverage", _target(payload),
              {"template": payload.kind, "butlers": payload.butlers, "replace": payload.replace,
               "guest_ids": payload.guest_ids, "days": [[d.isoformat(), e] for d, e in plan]})
        return {"written": len(plan)}
    return run(db, op, preview_flag, (payload.first, payload.last), principal)


@router.put("/day")
def set_day(payload: DayIn, preview_flag: bool = PREVIEW, principal: Principal = Depends(ASSIGN),
            db: Session = Depends(get_db)):
    def op():
        row = coverage.set_day(db, payload.scope(), payload.day, payload.employee_id, payload.overnight,
                               payload.comment)
        audit(db, principal, "stays_coverage", _target(payload),
              {"day": payload.day.isoformat(), "employee_id": payload.employee_id, "guest_ids": payload.guest_ids})
        return {"line_id": row.id if row else None}
    return run(db, op, preview_flag, (payload.day, payload.day), principal)


@router.put("/days")
def set_days(payload: DaysIn, preview_flag: bool = PREVIEW, principal: Principal = Depends(ASSIGN),
             db: Session = Depends(get_db)):
    """Назначение по дням (§6 «по дням»): одна операция, один предпросмотр."""
    days = [(x.day, x.employee_id) for x in payload.days]

    def op():
        n = coverage.set_days(db, payload.scope(), days)
        audit(db, principal, "stays_coverage", _target(payload),
              {"days": [[d.isoformat(), e] for d, e in days], "guest_ids": payload.guest_ids})
        return {"written": n}
    return run(db, op, preview_flag, (min(d for d, _ in days), max(d for d, _ in days)), principal)


@router.delete("/{line_id}")
def remove_line(line_id: int, preview_flag: bool = PREVIEW, principal: Principal = Depends(ASSIGN),
                db: Session = Depends(get_db)):
    row = db.get(CoverageLine, line_id)
    window = (row.day, row.day) if row else None

    def op():
        gone = coverage.delete_line(db, line_id)
        target = f"reservation:{gone.reservation_id}" if gone.reservation_id else f"group:{gone.group_id}"
        audit(db, principal, "stays_coverage", target,
              {"removed": {"day": gone.day.isoformat(), "employee_id": gone.employee_id, "line_id": line_id}})
        return {"ok": True}
    return run(db, op, preview_flag, window, principal)


def _target(p: ScopeIn) -> str:
    return f"reservation:{p.reservation_id}" if p.reservation_id else f"group:{p.group_id}"


def _ids(raw: str) -> list[int]:
    try:
        return [int(x) for x in raw.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=422, detail="Гости — номера через запятую") from None


@router.get("/candidates")
def get_candidates(day: dt.date, reservation_id: Optional[int] = None, group_id: Optional[int] = None,
                   guest_ids: str = "", principal: Principal = Depends(ASSIGN), db: Session = Depends(get_db)):
    try:
        return coverage.candidates(db, day, Scope(reservation_id, group_id, frozenset(_ids(guest_ids))),
                                   TimesheetDuty(db))
    except FundError as e:
        raise err(e) from e


@router.get("/replacements")
def get_replacements(first: dt.date, last: dt.date, principal: Principal = Depends(ASSIGN),
                     db: Session = Depends(get_db)):
    _span(first, last)
    return coverage.replacement_list(db, first, last, TimesheetDuty(db))


@router.post("/add-shift")
def add_shift(payload: AddShiftIn, principal: Principal = Depends(ASSIGN), db: Session = Depends(get_db)):
    """Смена Графика для батлера «вне смены»: два права, две записи журнала (§5)."""
    try:
        shifts = coverage.add_shift(db, principal_permissions(db, principal), payload.employee_id, payload.day,
                                    payload.shift_type_id, principal)
    except FundError as e:
        db.rollback()
        raise err(e) from e
    intervals = [[s.start_utc.isoformat(), s.end_utc.isoformat()] for s in shifts]
    audit(db, principal, "schedule_manual_shift", f"employee:{payload.employee_id}",
          {"date": payload.day.isoformat(), "shift_type_id": payload.shift_type_id, "shifts": intervals,
           "via": "stays"})
    audit(db, principal, "stays_add_shift", f"employee:{payload.employee_id}",
          {"date": payload.day.isoformat(), "shift_type_id": payload.shift_type_id})
    db.commit()
    return {"ok": True}
