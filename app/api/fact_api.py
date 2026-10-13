"""Вкладка «Факт» — слой 2 модели «График = 4 слоя» (16.4, T5).

Два представления одних и тех же отметок СКУД:

* ``GET /api/fact/sessions`` — история сессий «пришёл — ушёл» за произвольный
  диапазон на общем ядре pair_marks; моменты исходные, без округления и нарезки —
  визуализация (шкала, группировка по дням, подсветка ночных часов) строится
  фронтендом. Вкладка не зависит ни от чего, кроме отметок.
* ``GET /api/fact/day`` — сетка «Номера» (Q7): один день, все сотрудники — сырые
  отметки и их округление до шага, сопряжённые сессии, окно из кода Табеля,
  план / отработано / недостача / переработка по категориям и флаги из Графика.
  Числа — из движка (settle за период, содержащий день): клиент ничего не
  пересчитывает, шаг округления — из настроек, а не из интерфейса.
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import Principal
from ..db import get_db
from ..deps import TZ
from ..engine.application.errors import ApplicationError
from ..engine.application.months import month_period, period_containing
from ..engine.application.period_view import day_views
from ..engine.application.view_period import view_period
from ..engine.application.view_sessions import view_sessions
from ..engine.domain.sessions.pair_marks import pair_marks
from ..engine.domain.time.to_calc_mark import to_calc_mark
from ..engine.domain.types.errors import DomainError
from ..engine.interface.formatting import hm, local_hm
from ..engine.interface.views import flag_dict, session_view_dict
from ..models import Employee
from ..permissions import require_perm
from .engine_common import domain_error_text, emp_brief, engine_ports, now_utc, period_employees

router = APIRouter(prefix="/api/fact", tags=["fact"])


@router.get("/sessions")
def sessions(employee_id: int, first: dt.date, last: dt.date,
             principal: Principal = Depends(require_perm("presence.view")),
             db: Session = Depends(get_db)):
    if last < first or (last - first).days > 92:
        raise HTTPException(status_code=422, detail="Диапазон: не более 92 дней")
    if not principal.is_manager:
        own = principal.employee.id if principal.employee else None
        if own is None or own != employee_id:
            raise HTTPException(status_code=403,
                                detail="Доступна только своя история сессий")
    from_utc = dt.datetime.combine(first, dt.time(0), TZ).astimezone(dt.timezone.utc)
    to_utc = dt.datetime.combine(last + dt.timedelta(days=1), dt.time(0),
                                 TZ).astimezone(dt.timezone.utc)
    ports = engine_ports(db, principal, now_utc())
    try:
        views = view_sessions(str(employee_id), from_utc, to_utc, ports)
    except DomainError as exc:
        raise HTTPException(status_code=409, detail=domain_error_text(exc)) from exc
    emp = db.get(Employee, employee_id)
    return {"employee": emp_brief(emp) if emp else {"id": employee_id},
            "range": {"from": from_utc.isoformat(), "to": to_utc.isoformat(),
                      "first": first.isoformat(), "last": last.isoformat()},
            "sessions": [session_view_dict(v, TZ) for v in views]}


def _day_marks(eid: str, ports, st, day_lo: dt.datetime, day_hi: dt.datetime,
               tz) -> tuple[list[dict], list[dict]]:
    """Отметки дня: сырые моменты + округление до шага + сопряжённые сессии.

    Ядро то же, что у расчёта: ``to_calc_mark`` (RUL-ROUND-MOMENTS) и ``pair_marks``
    (R31/R32) с opening-отметкой до границ дня. Сессии обрезаются границами дня —
   Presence в движке тоже режется полуночью; открытый «пришёл» остаётся открытым.
    """
    marks = ports.punch.marks_between(eid, day_lo, day_hi)
    opening = ports.punch.last_mark_before(eid, day_lo)
    raw = [{"at": local_hm(m.at_utc, tz), "kind": m.kind,
            "rounded": local_hm(to_calc_mark(m, st).at_calc, tz)} for m in marks]
    calc = [to_calc_mark(m, st) for m in marks]
    opening_calc = to_calc_mark(opening, st) if opening is not None else None
    try:
        sessions = pair_marks(calc, opening_calc)
    except DomainError:
        # отметки дня уже санированы адаптером, но opening-отметка из предыдущего
        # дня теоретически может нарушить чередование — показываем отметки без сессий
        sessions = pair_marks(calc)
    segments = []
    for s in sessions:
        start = max(s.start, day_lo)
        if s.end is None:
            if start >= day_hi:
                continue
            segments.append({"start": local_hm(start, tz), "end": None, "open": True})
            continue
        end = min(s.end, day_hi)
        if start >= end:
            continue
        segments.append({"start": local_hm(start, tz), "end": local_hm(end, tz),
                         "open": False, "crosses_midnight": s.end > day_hi})
    return raw, segments


def _day_card(eid: str, date: dt.date, period, ports, st, now, tz) -> tuple[dict | None, str | None, bool]:
    """Карточка дня из settle периода: (card|None, error|None, out_of_staff)."""
    employment = ports.employment.employment(eid, period)
    if date < employment.start or (employment.end is not None and date > employment.end):
        return None, None, True
    try:
        view = view_period(eid, period, now, ports)
    except (DomainError, ApplicationError, ValueError) as exc:
        return None, domain_error_text(exc), False
    for dv in day_views(view):
        if dv.card.day != date:
            continue
        card = dv.card
        window = st.windows.get(card.timesheet_value)
        return {"timesheet_value": card.timesheet_value,
                "window": [hm(window.start_minute), hm(window.end_minute)] if window else None,
                "plan_minutes": card.plan_minutes,
                "timesheet_plan_minutes": dv.timesheet_plan_minutes,
                "fact_minutes": card.full_fact_minutes,
                "work_minutes": card.work_minutes,
                "overtime_minutes": card.overtime_minutes,
                "debt_minutes": card.debt_minutes,
                "codes": dict(card.codes),
                "pays_overtime": card.pays_overtime,
                "plan_equals_fact": card.plan_equals_fact_applied,
                "flags": [flag_dict(f, tz) for f in dv.flags]}, None, False
    # день не попал в карточки периода — за пределами эффективного трудоустройства
    return None, None, True


@router.get("/day")
def day_grid(date: dt.date,
             principal: Principal = Depends(require_perm("presence.view")),
             db: Session = Depends(get_db)):
    """Сетка «Номера» (слой 2 · Факт): один день глазами движка.

    Строки — сотрудники, трудоустроенные в этот день (R35); не-менеджер видит
    только себя. Период расчёта — содержащий день (месяц либо половина по
    настройке period_granularity); закрытый период читается из сохранённых
    результатов без пересчёта (RUL-CLOSED-PERIOD-IMMUTABLE).
    """
    now = now_utc()
    ports = engine_ports(db, principal, now)
    try:
        st = ports.settings.load(month_period(date.year, date.month))
    except (DomainError, ValueError) as exc:
        raise HTTPException(status_code=409,
                            detail=f"{domain_error_text(exc)}. Исправьте в разделе "
                                   "«Настройки» — сетка «Номера» не построится, пока "
                                   "конфигурация невалидна") from exc
    period = period_containing(date, st.period_granularity)
    emps = period_employees(db, date, date)
    if not principal.is_manager:
        own = principal.employee.id if principal.employee else None
        emps = [e for e in emps if own is not None and e.id == own]
    tz = st.tz
    day_lo = dt.datetime.combine(date, dt.time(0), tz).astimezone(dt.timezone.utc)
    day_hi = dt.datetime.combine(date + dt.timedelta(days=1), dt.time(0),
                                 tz).astimezone(dt.timezone.utc)
    rows = []
    for emp in emps:
        eid = str(emp.id)
        card, error, out_of_staff = _day_card(eid, date, period, ports, st, now, tz)
        marks, segments = _day_marks(eid, ports, st, day_lo, day_hi, tz)
        rows.append({"employee": emp_brief(emp), "error": error,
                     "out_of_staff": out_of_staff, "marks": marks,
                     "segments": segments, "card": card})
    return {"date": date.isoformat(),
            "period": {"start": period.start.isoformat(), "end": period.end.isoformat()},
            "granularity": st.period_granularity,
            "step_minutes": st.step_minutes,
            "tz": str(tz),
            "all_employees": principal.is_manager,
            "rows": rows}
