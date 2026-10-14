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
from ..deps import local_date
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


def _code_colors(db: Session) -> dict[str, str]:
    """Цвета кодов Табеля — блок presentation версии справочников (данные приложения).

    Домен подписей и цветов не знает (2.4): они лежат рядом со строкой CFG-DAY-CODES
    и читаются только интерфейсом. Пустой словарь — фронтенд берёт свою подстраховку.
    """
    ver = base_version(db, local_date())
    if ver is None:
        return {}
    try:
        payload = json.loads(ver.payload_json)
    except (ValueError, TypeError):
        return {}
    rows = payload.get("day_code_policy") or {}
    return {code: row["color"] for code, row in rows.items()
            if isinstance(row, dict) and row.get("color")}


@router.get("")
def get_tabel(year: int, month: int, half: Optional[int] = None,
              principal: Principal = Depends(require_perm("tabel.view")),
              db: Session = Depends(get_db)):
    if not (1 <= month <= 12 and 1 <= year <= 9999):
        raise HTTPException(status_code=422, detail="year должен быть 1..9999, month — 1..12")
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
            "colors": _code_colors(db),
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
    if len(payload.employee_ids) > 500 or len(payload.dates) > 366:
        raise HTTPException(status_code=422,
                            detail="Слишком большой запрос (максимум 500 сотрудников и 366 дат)")
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
    from ..employment import employed_on, periods_of

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
    period = _period_of(db, payload.year, payload.month, payload.half)
    st = _settings(db, period)
    p = ports(db, principal)
    emps: list[Employee] = []
    locked: list[int] = []
    for e in period_employees(db, period.start, period.end, payload.employee_ids):
        if timesheet_edit.lock_state(str(e.id), period.start, p) == "locked":
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
