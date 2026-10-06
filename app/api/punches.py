"""Отметки прихода/ухода: кнопки сотрудника, журнал посещений, «кто сейчас на смене»."""
from __future__ import annotations

import datetime as dt
import threading
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import Principal, audit, current_principal, require_manager
from ..db import get_db
from ..deps import local_date, now_local
from ..employment import employed_on, ensure_periods, periods_of
from ..models import Employee, Punch, ScheduleEntry
from ..schedule_helpers import shift_window
from .engine_common import bank_now, day_summary

# окно поиска открытой смены вокруг плана (интерфейс отметок; на расчёт часов не влияет)
WINDOW_BEFORE_H = 4
WINDOW_AFTER_H = 6
GRACE_MINUTES = 5


def load_rules(db: Session) -> dict:
    """Лимит опоздания для подсветки на экранах — из настроек движка (Т7)."""
    from ..engine.adapters.sql_settings import SqlSettingsAdapter
    from ..engine.application.periods import month_period
    today = local_date()
    try:
        return {"grace_minutes": SqlSettingsAdapter(db).load(month_period(today.year, today.month)).late_limit_minutes}
    except Exception:  # noqa: BLE001 — экран отметок не должен падать из-за настроек
        return {"grace_minutes": GRACE_MINUTES}

router = APIRouter(prefix="/api/punches", tags=["punches"])

# повторное нажатие той же кнопки в этот промежуток — дубль (двойной тап, повтор запроса)
DUPLICATE_WINDOW = dt.timedelta(seconds=60)
# сериализация отметок одного сотрудника внутри процесса: два одновременных запроса
# не должны оба увидеть «смена не открыта» и записать два IN
_emp_locks: dict[int, threading.Lock] = defaultdict(threading.Lock)
_emp_locks_guard = threading.Lock()


def _lock_for(emp_id: int) -> threading.Lock:
    with _emp_locks_guard:
        return _emp_locks[emp_id]


class PunchIn(BaseModel):
    kind: str = "auto"        # in | out | auto
    note: str = ""
    employee_id: Optional[int] = None  # только для менеджера (ручная отметка за сотрудника)
    ts: Optional[str] = None           # только для менеджера: отметка задним числом (ISO, локальное время)


def _employed_on(db: Session, emp: Employee, date: dt.date) -> bool:
    """Работал ли сотрудник в компании в эту дату (приём → увольнение → повторный приём)."""
    periods = periods_of(db, emp.id) or ensure_periods(db, emp)
    return employed_on(periods, date)


def _resolve_employee(principal: Principal, employee_id: Optional[int], db: Session) -> Employee:
    if principal.is_manager and employee_id:
        emp = db.get(Employee, employee_id)
        if not emp:
            raise HTTPException(status_code=404, detail="Сотрудник не найден")
        return emp
    if principal.employee:
        return principal.employee
    raise HTTPException(status_code=403, detail="К вашей учётной записи не привязан сотрудник")


def _plan_for_date(db: Session, emp_id: int, today: dt.date, rules: dict,
                   at_ts: Optional[dt.datetime] = None, *, emp: Optional[Employee] = None,
                   entries: Optional[dict] = None, index=None, catalog=None,
                   cfg: Optional[dict] = None, employed: Optional[bool] = None):
    """План на «сегодня» (ручная ячейка или базовый цикл); если сейчас раннее утро —
    смотрим и вчерашнюю ночную смену.

    entries/index/catalog/cfg — предзагруженные данные: нужны в «Кто на работе»,
    где план спрашивается для каждого сотрудника (иначе ~5 запросов на человека
    каждые 30 секунд у каждого открытого клиента).
    """
    from ..base_schedule import base_shift

    if emp is None:
        emp = db.get(Employee, emp_id)
    yesterday = today - dt.timedelta(days=1)
    if entries is not None:
        entry = entries.get((emp_id, today))
        y_entry = entries.get((emp_id, yesterday))
    else:
        entry = db.scalar(select(ScheduleEntry).where(
            ScheduleEntry.employee_id == emp_id, ScheduleEntry.date == today))
        y_entry = db.scalar(select(ScheduleEntry).where(
            ScheduleEntry.employee_id == emp_id, ScheduleEntry.date == yesterday))
    # семантика прежняя: план «на сегодня» берётся из текущей строки словаря
    # (entry.shift_type подгружен JOIN'ом при пакетной выборке — запроса нет)
    shift = entry.shift_type if entry else None
    if shift is None and emp is not None:
        shift = base_shift(db, emp, today, cfg=cfg, employed=employed,
                           index=index, catalog=catalog)
    p_start, p_end = shift_window(shift, today, rules)

    y_shift = y_entry.shift_type if y_entry else None
    if y_shift is None and emp is not None:
        y_shift = base_shift(db, emp, yesterday, cfg=cfg, employed=employed,
                             index=index, catalog=catalog)
    y_start, y_end = shift_window(y_shift, yesterday, rules)

    now = at_ts or now_local()
    active_yesterday = bool(y_start and y_end and y_start <= now <= y_end + dt.timedelta(hours=WINDOW_AFTER_H))
    if active_yesterday and (not p_start or now < p_start):
        return y_entry, y_shift, y_start, y_end, yesterday
    return entry, shift, p_start, p_end, today


def _plan_for(db: Session, emp_id: int, today: dt.date, rules: dict):
    return _plan_for_date(db, emp_id, today, rules)


def _open_session(db: Session, emp_id: int, since: dt.datetime) -> Optional[Punch]:
    """Последний IN, после которого нет OUT."""
    punches = db.scalars(select(Punch).where(
        Punch.employee_id == emp_id, Punch.ts >= since).order_by(Punch.ts)).all()
    last_in = None
    for p in punches:
        if p.kind == "IN":
            last_in = p
        else:
            last_in = None
    return last_in


def _status_payload(db: Session, emp: Employee) -> dict:
    rules = load_rules(db)
    today = local_date()
    entry, shift, p_start, p_end, plan_date = _plan_for(db, emp.id, today, rules)
    since = (p_start - dt.timedelta(hours=WINDOW_BEFORE_H)) if p_start \
        else dt.datetime(today.year, today.month, today.day) - dt.timedelta(hours=12)
    open_in = _open_session(db, emp.id, since)
    now = now_local()

    last_punch = db.scalar(select(Punch).where(Punch.employee_id == emp.id)
                           .order_by(Punch.ts.desc()).limit(1))
    elapsed = round((now - open_in.ts).total_seconds() / 3600.0, 1) if open_in else None
    is_late = bool(p_start and open_in and open_in.ts > p_start + dt.timedelta(minutes=rules["grace_minutes"]))

    summary = day_summary(db, emp, plan_date)
    # ворот отметок нет (спец. v4, Р5): отмечаться можно всегда, а отметки в днях отсутствия
    # получают информационный флаг «Активность требует проверки»
    in_ok, out_ok = True, True

    return {
        "now": now.isoformat(timespec="seconds"),
        "today": today.isoformat(),
        "plan_date": plan_date.isoformat(),
        "punch_in_allowed": in_ok,
        "punch_out_allowed": out_ok,
        "shift": None if not shift else {
            "code": shift.code, "name": shift.name, "kind": shift.kind, "color": shift.color,
            "display_code": shift.display_code, "start": shift.start_time, "end": shift.end_time,
            "overnight": shift.overnight, "planned_hours": shift.planned_hours,
            "is_default_off": shift.is_default_off, "tzh_code": shift.tzh_code,
        },
        "note": entry.note if entry else "",
        "planned_start": p_start.isoformat(timespec="minutes") if p_start else None,
        "planned_end": p_end.isoformat(timespec="minutes") if p_end else None,
        "on_shift": open_in is not None,
        "session_start": open_in.ts.isoformat(timespec="minutes") if open_in else None,
        "elapsed_hours": elapsed,
        "is_late": is_late,
        "last_punch": None if not last_punch else {
            "kind": last_punch.kind, "ts": last_punch.ts.isoformat(timespec="minutes"),
            "source": last_punch.source},
        "today_fact": {k: summary[k] for k in ("fact_hours", "night_hours", "ot_hours", "status", "value")},
        "balance_hours": bank_now(db, emp, now_local().date()),
    }


@router.get("/status")
def my_status(principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Состояние для личного кабинета: план на сегодня, на смене ли я, сколько отработал."""
    emp = _resolve_employee(principal, None, db)
    return _status_payload(db, emp)


@router.post("")
def punch(payload: PunchIn, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Кнопки «Пришёл на работу» / «Ушёл с работы»."""
    emp = _resolve_employee(principal, payload.employee_id, db)
    with _lock_for(emp.id):
        return _punch_locked(payload, principal, db, emp)


def _punch_locked(payload: PunchIn, principal: Principal, db: Session, emp: Employee):
    rules = load_rules(db)
    now = now_local()
    backfill = False
    ts = now

    if payload.ts:
        if not principal.is_manager:
            raise HTTPException(status_code=403, detail="Отметку задним числом может поставить только менеджер")
        try:
            ts = dt.datetime.fromisoformat(payload.ts.replace("Z", ""))
        except ValueError:
            raise HTTPException(status_code=422, detail="Некорректный формат времени (ожидается ISO, например 2026-09-20T08:00)")
        if ts.tzinfo is not None:
            raise HTTPException(status_code=422, detail="Время должно быть локальным, без часового пояса")
        if ts > now:
            raise HTTPException(status_code=422, detail="Отметка не может быть в будущем")
        if now - ts > dt.timedelta(days=62):
            raise HTTPException(status_code=422, detail="Слишком старая отметка (максимум 2 месяца)")
        backfill = True

    target_date = ts.date()
    entry, shift, p_start, p_end, plan_date = _plan_for_date(db, emp.id, target_date, rules, at_ts=ts)
    if not _employed_on(db, emp, plan_date):
        raise HTTPException(status_code=409,
                            detail="Отметку поставить нельзя: в эту дату сотрудник не работал в компании "
                                   "(до приёма или после увольнения)")
    since = (p_start - dt.timedelta(hours=WINDOW_BEFORE_H)) if p_start \
        else dt.datetime(target_date.year, target_date.month, target_date.day) - dt.timedelta(hours=12)
    open_in = _open_session(db, emp.id, since)

    kind = payload.kind
    if kind == "auto":
        kind = "OUT" if open_in else "IN"
    kind = kind.upper()
    if kind not in ("IN", "OUT"):
        raise HTTPException(status_code=422, detail="kind должен быть in/out/auto")
    if kind == "OUT" and not open_in:
        if not backfill:
            raise HTTPException(status_code=409, detail="Нет открытой смены: сначала нажмите «Пришёл на работу»")
    if not backfill:
        if kind == "IN" and open_in:
            raise HTTPException(status_code=409,
                                detail=f"Вы уже на смене с {open_in.ts:%H:%M} — повторная отметка прихода не нужна")
        # «auto» сам выбирает направление, поэтому двойной тап превратился бы в IN+OUT за секунду;
        # явные in/out от дублей уже защищены проверками выше
        last = db.scalar(select(Punch).where(Punch.employee_id == emp.id)
                         .order_by(Punch.ts.desc()).limit(1)) if payload.kind == "auto" else None
        if last and abs(now - last.ts) < DUPLICATE_WINDOW:
            what = "приход" if last.kind == "IN" else "уход"
            raise HTTPException(status_code=409,
                                detail=f"Отметка уже принята: {what} в {last.ts:%H:%M}. "
                                       "Следующую можно поставить через минуту")
    if backfill:
        # при корректировке задним числом пара IN/OUT определяется по уже имеющимся отметкам дня
        day_punches = db.scalars(select(Punch).where(
            Punch.employee_id == emp.id, Punch.ts >= dt.datetime(target_date.year, target_date.month, target_date.day),
            Punch.ts < dt.datetime(target_date.year, target_date.month, target_date.day) + dt.timedelta(days=2),
        )).all()
        if payload.kind == "auto":
            kind = "OUT" if any(p.kind == "IN" for p in day_punches) and not any(
                p.kind == "OUT" for p in day_punches) else "IN"

    # Ворот отметок нет (спец. v4, Р5, раздел 17): все реальные отметки участвуют в расчёте.

    source = "manual" if backfill or (principal.is_manager and payload.employee_id and payload.employee_id != (
        principal.employee.id if principal.employee else None)) else "web"
    p = Punch(employee_id=emp.id, ts=ts, kind=kind, source=source,
              created_by=principal.user.id, note=payload.note or ("корректировка менеджером" if backfill else ""))
    db.add(p)
    audit(db, principal, "punch_" + kind.lower() + ("_backfill" if backfill else ""), f"employee:{emp.id}",
          {"ts": ts.isoformat(timespec="minutes"), "source": source})
    db.commit()
    row = day_summary(db, emp, plan_date)

    warnings = []
    if backfill:
        warnings.append("Отметка добавлена задним числом — действие записано в журнал аудита")
    if not shift or shift.kind != "work":
        warnings.append("По графику в этот день смены нет — отметка сохранена; работа без плана "
                        "учитывается как переработка (коды ДЯ/ДН), руководитель увидит флаг")
    if "ACTIVITY_REQUIRES_REVIEW" in row["flags"]:
        warnings.append(f"В Табеле день «{row['value']}» — отметка помечена для проверки руководителем")
    if row["ot_hours"]:
        warnings.append(f"Переработка {row['ot_hours']:g} ч учтена в управленческом табеле")

    status = _status_payload(db, emp)
    day_prefix = "" if ts.date() == now.date() else f"{ts:%d.%m} "
    message = (f"Отмечен приход {day_prefix}в {ts:%H:%M}" if kind == "IN"
               else f"Отмечен уход {day_prefix}в {ts:%H:%M}")
    return {"ok": True, "message": message, "backfill": backfill, "plan_date": plan_date.isoformat(),
            "punch": {"id": p.id, "kind": p.kind, "ts": p.ts.isoformat(timespec="minutes"),
                      "source": p.source, "rounded_to_hour": True},
            "day": {k: row[k] for k in ("planned_hours", "fact_hours", "night_hours", "ot_hours",
                                        "deficit_hours", "status")},
            "warnings": warnings, "status": status}


@router.get("")
def list_punches(date: Optional[dt.date] = None, year: Optional[int] = None, month: Optional[int] = None,
                 employee_id: Optional[int] = None, principal: Principal = Depends(current_principal),
                 db: Session = Depends(get_db)):
    """Журнал отметок. Сотрудник видит только свои, менеджер — всех."""
    stmt = select(Punch).order_by(Punch.ts.desc())   # employee подгружается JOIN'ом (lazy="joined")
    limit = 2000
    if not principal.is_manager:
        if not principal.employee:
            raise HTTPException(status_code=403, detail="Нет привязанного сотрудника")
        stmt = stmt.where(Punch.employee_id == principal.employee.id)
    elif employee_id:
        stmt = stmt.where(Punch.employee_id == employee_id)

    if date:
        lo = dt.datetime(date.year, date.month, date.day)
        stmt = stmt.where(Punch.ts >= lo, Punch.ts < lo + dt.timedelta(days=1))
    elif year and month:
        lo = dt.datetime(year, month, 1)
        hi = dt.date(year + 1, 1, 1) if month == 12 else dt.date(year, month + 1, 1)
        stmt = stmt.where(Punch.ts >= lo, Punch.ts < dt.datetime(hi.year, hi.month, hi.day))
    else:
        limit = 500   # без фильтра по дате — только последние отметки

    punches = db.scalars(stmt.limit(limit)).all()
    return [{
        "id": p.id, "employee_id": p.employee_id,
        "employee": p.employee.display_name if p.employee else "",
        "position": p.employee.position if p.employee else "",
        "ts": p.ts.isoformat(timespec="minutes"), "kind": p.kind,
        "source": p.source, "note": p.note,
        "created_by": p.created_by,
    } for p in punches]


@router.delete("/{punch_id}")
def delete_punch(punch_id: int, principal: Principal = Depends(require_manager), db: Session = Depends(get_db)):
    """Отменить ошибочную отметку (с пересчётом табеля и записью в аудит)."""
    p = db.get(Punch, punch_id)
    if not p:
        raise HTTPException(status_code=404, detail="Отметка не найдена")
    ts, emp_id = p.ts, p.employee_id
    audit(db, principal, "punch_delete", f"punch:{punch_id}",
          {"employee_id": emp_id, "ts": ts.isoformat(timespec="minutes"), "kind": p.kind})
    db.delete(p)
    db.commit()   # пересчёт не нужен: движок считает Табель/УТ при чтении
    return {"ok": True}


class NoteIn(BaseModel):
    note: str


@router.put("/{punch_id}/note")
def set_punch_note(punch_id: int, payload: NoteIn,
                   principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Описание переработки: с кем работал и что делал (ставит сотрудник или менеджер)."""
    p = db.get(Punch, punch_id)
    if not p:
        raise HTTPException(status_code=404, detail="Отметка не найдена")
    if not principal.is_manager and (not principal.employee or principal.employee.id != p.employee_id):
        raise HTTPException(status_code=403, detail="Можно комментировать только свои отметки")
    p.note = payload.note.strip()[:500]
    audit(db, principal, "punch_note", f"punch:{punch_id}", {"note": p.note})
    db.commit()
    return {"ok": True, "note": p.note}
