"""Отметки прихода/ухода: кнопки сотрудника, журнал посещений, статус «я на смене».

Экран отметок НЕ запускает тяжёлый конвейер (16.1 п.2): план на сегодня — из Графика
(schedule_shifts, порождён из Табеля), ожидаемые подинтервалы — доменными функциями
Графика (schedule/), «на работе с …» — по последней отметке; банк — последний закрытый
период из хранилища (чтение без домена, RUL-CLOSED-PERIOD-IMMUTABLE). Точные часы,
переработки и недостача «сегодня» — только во вкладке «Управленческий табель».

Ввод отметок гарантирует чередование «пришёл»/«ушёл» на точке входа (первая линия
контроля последовательности, 7.4 п.4): повторный «пришёл» отклоняется, «ушёл» без
открытой смены — только корректировкой менеджера."""
from __future__ import annotations

import datetime as dt
import threading
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal, current_principal
from app.core.db import get_db
from app.core.permissions import has_perm, require_perm
from app.core.time import TZ, local_date, now_local
from app.modules.employees.application import Employee, employed_on, ensure_periods, periods_of

from ..adapters.orm import Punch, ScheduleAbsence, TabelDay
from ..application.engine_common import day_code_rows, last_closed_bank
from ..application.punch_plan import (
    plan_for_date as _plan_for_date,
)
from ..application.punch_plan import (
    to_local as _to_local,
)

# Grace-период опоздания. Окно поиска открытой сессии больше не нужно:
# открытая сессия ищется по всей истории — как на доске (решение владельца
# 15.10.2026: смены длительностью сутки и более — норма, см. ADR-0009)
GRACE_MINUTES = 5


def load_rules(db: Session) -> dict:
    """Лимит опоздания для подсветки на экранах — из настроек движка (CFG-LIMITS)."""
    from ..adapters.sql_settings import SqlSettingsAdapter
    from ..application.months import month_period
    today = local_date()
    try:
        st = SqlSettingsAdapter(db).load(month_period(today.year, today.month))
        return {"grace_minutes": st.late_limit_minutes}
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


def _open_session(db: Session, emp_id: int) -> Optional[Punch]:
    """Открытая сессия = последняя по времени (ts, id) отметка является «пришёл».

    Окно — вся история, ровно как на доске «кто на работе» (last_marks):
    сотрудник может легально быть на смене сутки и более (решение владельца
    15.10.2026, ADR-0009). Прежнее окно «план − 4 ч» обрезало длинные сессии:
    личный экран предлагал «Пришёл» при фактически открытой сессии, а расчёт
    всё равно склеивал сессии (sanitize адаптера отбрасывает повторный IN) —
    окно не защищало расчёт, а лишь разводило экраны (дефект 15.10.2026).
    """
    last = db.scalar(select(Punch).where(Punch.employee_id == emp_id)
                     .order_by(Punch.ts.desc(), Punch.id.desc()).limit(1))
    return last if last is not None and last.kind == "IN" else None


def _punch_permissions(db: Session, emp_id: int,
                       now: dt.datetime) -> tuple[bool, bool, Optional[str]]:
    """Можно ли сейчас нажать «Пришёл»/«Ушёл» — и текст статуса для подсказки.

    Два слоя, оба соблюдает СЕРВЕР (решение владельца 16.10.2026: прежде флаги
    читал только фронтенд, прямой запрос к API обходил запрет):

    * покрывающее согласованное отсутствие — режим из словарного вида
      (например, «Отпросился»);
    * код Табеля сегодняшнего дня — режим из карточки кода (punch_in/punch_out):
      отпуск «ОТ» отмечается заявлением, а не отметками. Отсутствующий ключ
      в старой версии справочников — разрешение (RUL-ALL-MARKS-COUNTED)."""
    now_utc = now.replace(tzinfo=TZ).astimezone(dt.timezone.utc).replace(tzinfo=None)
    in_ok, out_ok, hint = True, True, None
    row = db.scalar(select(ScheduleAbsence).where(
        ScheduleAbsence.employee_id == emp_id, ScheduleAbsence.start_utc <= now_utc,
        ScheduleAbsence.end_utc > now_utc, ScheduleAbsence.kind_id.is_not(None)).limit(1))
    if row is not None and row.kind is not None:
        in_ok = bool(row.kind.punch_in_allowed)
        out_ok = bool(row.kind.punch_out_allowed)
        if not (in_ok and out_ok):
            hint = f"сейчас статус: {row.kind.name}"
    day = now.date()
    trow = db.scalar(select(TabelDay).where(TabelDay.employee_id == emp_id,
                                            TabelDay.date == day))
    if trow is not None:
        crow = day_code_rows(db, day).get(trow.code)
        if crow is not None and not (crow["punch_in"] and crow["punch_out"]):
            in_ok = in_ok and crow["punch_in"]
            out_ok = out_ok and crow["punch_out"]
            if hint is None:
                hint = f"сейчас статус: {crow['title'] or trow.code}"
    return in_ok, out_ok, hint


def _today_punched_hours(db: Session, emp_id: int, day: dt.date) -> float:
    """Часы «сегодня» по отметкам (спаренные IN/OUT внутри дня) — справочно для экрана;
    точный расчёт — в Управленческом табеле (16.1 п.2)."""
    lo = dt.datetime(day.year, day.month, day.day)
    rows = db.scalars(select(Punch).where(Punch.employee_id == emp_id, Punch.ts >= lo,
                                          Punch.ts < lo + dt.timedelta(days=1))
                      .order_by(Punch.ts, Punch.id)).all()
    total, open_since = 0.0, None
    now = now_local()
    for p in rows:
        if p.kind == "IN":
            open_since = p.ts
        elif open_since is not None:
            total += (p.ts - open_since).total_seconds() / 3600.0
            open_since = None
    if open_since is not None:
        total += (now - open_since).total_seconds() / 3600.0
    return round(total, 1)


def _status_payload(db: Session, emp: Employee) -> dict:
    rules = load_rules(db)
    today = local_date()
    shift, p_start, p_end, plan_date, subs = _plan_for_date(db, emp.id, today)
    open_in = _open_session(db, emp.id)
    now = now_local()
    last_punch = db.scalar(select(Punch).where(Punch.employee_id == emp.id)
                           .order_by(Punch.ts.desc()).limit(1))
    elapsed = round((now - open_in.ts).total_seconds() / 3600.0, 1) if open_in else None
    first_expected = subs[0][0] if subs else None
    is_late = bool(first_expected and not open_in
                   and now > _to_local(first_expected) + dt.timedelta(minutes=rules["grace_minutes"]))
    in_ok, out_ok, hint = _punch_permissions(db, emp.id, now)
    bank_hours, bank_period = last_closed_bank(db, emp.id)

    return {
        "now": now.isoformat(timespec="seconds"),
        "today": today.isoformat(),
        "plan_date": plan_date.isoformat(),
        "punch_in_allowed": in_ok,
        "punch_out_allowed": out_ok,
        "punch_status_hint": hint,
        "shift": shift,
        "planned_start": p_start.isoformat(timespec="minutes") if p_start else None,
        "planned_end": p_end.isoformat(timespec="minutes") if p_end else None,
        "expected": [[_to_local(a).strftime("%H:%M"), _to_local(b).strftime("%H:%M")]
                     for a, b in subs],
        "on_shift": open_in is not None,
        "session_start": open_in.ts.isoformat(timespec="minutes") if open_in else None,
        "elapsed_hours": elapsed,
        "is_late": is_late,
        "last_punch": None if not last_punch else {
            "kind": last_punch.kind, "ts": last_punch.ts.isoformat(timespec="minutes"),
            "source": last_punch.source},
        "today_hours": _today_punched_hours(db, emp.id, today),
        "balance_hours": bank_hours if bank_hours is not None else 0.0,
        "balance_period": None if bank_period is None else
        {"start": bank_period.start.isoformat(), "end": bank_period.end.isoformat()},
        "balance_note": "банк последнего закрытого периода; живой итог — в «Управленческом табеле»",
    }


@router.get("/status")
def my_status(principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Состояние для личного кабинета: план на сегодня, на смене ли я, сколько отработал."""
    emp = _resolve_employee(principal, None, db)
    return _status_payload(db, emp)


def _need(principal: Principal, db: Session, key: str) -> None:
    if not has_perm(db, principal, key):
        raise HTTPException(status_code=403, detail=f"Недостаточно прав: {key}")


@router.post("")
def punch(payload: PunchIn, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Кнопки «Пришёл на работу» / «Ушёл с работы».

    Права: отметка за себя — me.punch; чужая отметка или отметка задним числом — punches.manage.
    """
    self_id = principal.employee.id if principal.employee else None
    if payload.ts or (payload.employee_id is not None and payload.employee_id != self_id):
        _need(principal, db, "punches.manage")
    else:
        _need(principal, db, "me.punch")
    emp = _resolve_employee(principal, payload.employee_id, db)
    with _lock_for(emp.id):
        return _punch_locked(payload, principal, db, emp)


def _punch_locked(payload: PunchIn, principal: Principal, db: Session, emp: Employee):
    # Межпроцессное взаимное исключение: threading.Lock в punch() защищает только
    # внутри процесса. При нескольких воркерах/инстансах гонку «прочитал состояние —
    # вставил отметку» закрывает блокировка строки сотрудника: Postgres выполняет
    # SELECT … FOR UPDATE, SQLite форсу игнорирует — там писатели и так
    # сериализуются файловой блокировкой (WAL + busy_timeout).
    db.execute(select(Employee).where(Employee.id == emp.id).with_for_update())
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
    shift, p_start, _p_end, plan_date, _subs = _plan_for_date(db, emp.id, target_date, at_ts=ts)
    if not _employed_on(db, emp, plan_date):
        raise HTTPException(status_code=409,
                            detail="Отметку поставить нельзя: в эту дату сотрудник не работал в компании "
                                   "(до приёма или после увольнения)")
    open_in = _open_session(db, emp.id)

    kind = payload.kind
    if kind == "auto":
        kind = "OUT" if open_in else "IN"
    kind = kind.upper()
    if kind not in ("IN", "OUT"):
        raise HTTPException(status_code=422, detail="kind должен быть in/out/auto")
    if not backfill:
        # Режим отметок соблюдается на сервере (находка 16.10.2026): флаги вида
        # отсутствия и карточки кода Табеля раньше читал только фронтенд — прямой
        # запрос к API позволял отметиться в отпуске. Корректировка задним числом
        # (backfill, инструмент менеджера) этому ограничению не подлежит.
        in_ok, out_ok, hint = _punch_permissions(db, emp.id, now)
        if (kind == "IN" and not in_ok) or (kind == "OUT" and not out_ok):
            what = "приход" if kind == "IN" else "уход"
            raise HTTPException(status_code=409,
                                detail=f"Отметку поставить нельзя: {hint or 'отметки ограничены'}"
                                       f" — отмечать {what} запрещено")
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
    if backfill and payload.kind == "auto":
        # при корректировке задним числом пара IN/OUT определяется по уже имеющимся отметкам дня
        day_punches = db.scalars(select(Punch).where(
            Punch.employee_id == emp.id,
            Punch.ts >= dt.datetime(target_date.year, target_date.month, target_date.day),
            Punch.ts < dt.datetime(target_date.year, target_date.month, target_date.day)
            + dt.timedelta(days=2))).all()
        kind = "OUT" if any(p.kind == "IN" for p in day_punches) and not any(
            p.kind == "OUT" for p in day_punches) else "IN"

    # Ворот отметок нет (RUL-ALL-MARKS-COUNTED): все реальные отметки участвуют в расчёте.

    source = "manual" if backfill or (principal.is_manager and payload.employee_id
                                      and payload.employee_id !=
                                      (principal.employee.id if principal.employee else None)) \
        else "web"
    p = Punch(employee_id=emp.id, ts=ts, kind=kind, source=source,
              created_by=principal.user.id,
              note=payload.note or ("корректировка менеджером" if backfill else ""))
    db.add(p)
    audit(db, principal, "punch_" + kind.lower() + ("_backfill" if backfill else ""),
          f"employee:{emp.id}", {"ts": ts.isoformat(timespec="minutes"), "source": source})
    db.commit()

    warnings = []
    if backfill:
        warnings.append("Отметка добавлена задним числом — действие записано в журнал аудита")
    if shift is None:
        warnings.append("По Графику в этот день смены нет — отметка сохранена; работа без плана "
                        "учитывается как переработка (коды ДЯ/ДН), руководитель увидит флаг "
                        "«Работа вне Графика»")
    status = _status_payload(db, emp)
    day_prefix = "" if ts.date() == now.date() else f"{ts:%d.%m} "
    message = (f"Отмечен приход {day_prefix}в {ts:%H:%M}" if kind == "IN"
               else f"Отмечен уход {day_prefix}в {ts:%H:%M}")
    return {"ok": True, "message": message, "backfill": backfill,
            "plan_date": plan_date.isoformat(),
            "punch": {"id": p.id, "kind": p.kind, "ts": p.ts.isoformat(timespec="minutes"),
                      "source": p.source},
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
def delete_punch(punch_id: int, principal: Principal = Depends(require_perm("punches.manage")), db: Session = Depends(get_db)):
    """Отменить ошибочную отметку (с записью в аудит)."""
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
