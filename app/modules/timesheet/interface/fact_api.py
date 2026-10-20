"""Вкладка «Факт» — слой 2 модели «График = 4 слоя» (16.4, T5).

Три представления одних и тех же отметок СКУД:

* ``GET /api/fact/sessions`` — история сессий «пришёл — ушёл» за произвольный
  диапазон на общем ядре pair_marks; моменты исходные, без округления и нарезки —
  визуализация (шкала, группировка по дням, подсветка ночных часов) строится
  фронтендом. Вкладка не зависит ни от чего, кроме отметок.
* ``GET /api/fact/month`` — гант «Месяц» (16.10.2026): округлённые сессии целиком
  на непрерывной оси времени (смена через полночь — одна полоса), окно Табеля
  и цвет словарной смены на день, согласованные отсутствия; без settle.
* ``GET /api/fact/day`` — сетка «День» (Q7): один день, все сотрудники — сырые
  отметки и их округление до шага, сопряжённые сессии, окно из кода Табеля,
  план / отработано / недостача / переработка по категориям и флаги из Графика.
  Числа — из движка (settle за период, содержащий день): клиент ничего не
  пересчитывает, шаг округления — из настроек, а не из интерфейса.
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm
from app.core.time import TZ
from app.modules.employees.application import Employee

from ..application.engine_common import emp_brief, engine_ports, now_utc, period_employees
from ..application.errors import ApplicationError
from ..application.months import month_period, period_containing
from ..application.period_view import day_views
from ..application.view_period import view_period
from ..application.view_sessions import view_sessions
from ..domain.day_card.fmt_hours import fmt_hours
from ..domain.sessions.pair_marks import pair_marks
from ..domain.time.to_calc_mark import to_calc_mark
from ..domain.types.errors import DomainError
from .formatting import error_text, hm, local_hm
from .views import flag_dict, session_view_dict

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
    # DomainError → 422 — централизованный хэндлер main.py (§5.3)
    views = view_sessions(str(employee_id), from_utc, to_utc, ports)
    emp = db.get(Employee, employee_id)
    return {"employee": emp_brief(emp) if emp else {"id": employee_id},
            "range": {"from": from_utc.isoformat(), "to": to_utc.isoformat(),
                      "first": first.isoformat(), "last": last.isoformat()},
            "sessions": [session_view_dict(v, TZ) for v in views]}


@router.get("/month")
def fact_month(year: int, month: int, principal: Principal = Depends(require_perm("presence.view")),
               db: Session = Depends(get_db)):
    """Слой 2, вкладка «Месяц» (16.10.2026): Гант фактических присутствий за месяц.

    Ось X — непрерывное время месяца (не колонки дней), поэтому смена через
    полночь — ОДНА полоса: сессии берём сопряжением ОКРУГЛЁННЫХ отметок
    (to_calc_mark + pair_marks, то же ядро, что у «Дня») ЦЕЛИКОМ, без нарезки
    полуночью. На день отдаём стандартное окно Табеля (штриховка), цвет полосы
    (словарь «Смены и отсутствия», общий с Графиком) и согласованные отсутствия.
    Числа расчёта (план/недостача) Ганту не нужны — settle не запускаем."""
    from ..adapters.orm import ScheduleAbsence, ScheduleShift, ShiftType, TabelDay
    from ..application.engine_common import color_lookups, covers_window, pick_cell_color

    if not (1 <= month <= 12 and 1 <= year <= 9999):
        raise HTTPException(status_code=422, detail="year должен быть 1..9999, month — 1..12")
    period = month_period(year, month)
    st = _settings_for_period(db, period)
    emps = period_employees(db, period.start, period.end)
    if not principal.is_manager:
        own = principal.employee.id if principal.employee else None
        emps = [e for e in emps if e.id == own]
    ports = engine_ports(db, principal, now_utc())
    lo = dt.datetime.combine(period.start, dt.time(0), TZ)
    hi = dt.datetime.combine(period.end + dt.timedelta(days=1), dt.time(0), TZ)
    lookups = color_lookups(db)
    emp_ids = [e.id for e in emps]
    tabel_rows: dict[tuple[int, dt.date], TabelDay] = {
        (r.employee_id, r.date): r for r in db.scalars(select(TabelDay).where(
            TabelDay.employee_id.in_(emp_ids), TabelDay.date >= period.start,
            TabelDay.date <= period.end))} if emp_ids else {}
    lo_utc = lo.astimezone(dt.timezone.utc).replace(tzinfo=None)
    hi_utc = hi.astimezone(dt.timezone.utc).replace(tzinfo=None)
    absence_rows = list(db.scalars(select(ScheduleAbsence).where(
        ScheduleAbsence.employee_id.in_(emp_ids), ScheduleAbsence.start_utc < hi_utc,
        ScheduleAbsence.end_utc > lo_utc))) if emp_ids else []
    absences_by_emp: dict[int, list] = {}
    for a in absence_rows:
        absences_by_emp.setdefault(a.employee_id, []).append(a)
    kinds = {k.id: k for k in db.scalars(select(ShiftType).where(
        ShiftType.id.in_({a.kind_id for a in absence_rows if a.kind_id})))} \
        if absence_rows else {}
    # цвета полос — как в сетке Графика: по сменам месяца (якорь и соседи)
    shift_rows = list(db.scalars(select(ScheduleShift).where(
        ScheduleShift.employee_id.in_(emp_ids), ScheduleShift.start_utc < hi_utc,
        ScheduleShift.end_utc > lo_utc).order_by(ScheduleShift.start_utc))) if emp_ids else []
    shifts_by_emp_day: dict[tuple[int, str], list] = {}
    for r in shift_rows:
        s_local = r.start_utc.replace(tzinfo=dt.timezone.utc).astimezone(TZ)
        e_local = r.end_utc.replace(tzinfo=dt.timezone.utc).astimezone(TZ)
        d0 = s_local.date()
        while d0 <= min(e_local.date(), period.end):
            if period.start <= d0:
                shifts_by_emp_day.setdefault((r.employee_id, d0.isoformat()), []).append(r)
            d0 += dt.timedelta(days=1)
    days = [period.start + dt.timedelta(days=i)
            for i in range((period.end - period.start).days + 1)]
    rows = []
    for e in emps:
        eid = str(e.id)
        marks = ports.punch.marks_between(eid, lo, hi)
        opening = ports.punch.last_mark_before(eid, lo)
        calc = [to_calc_mark(m, st) for m in marks]
        opening_calc = to_calc_mark(opening, st) if opening is not None else None
        try:
            sessions = pair_marks(calc, opening_calc)
        except DomainError:
            sessions = pair_marks(calc)
        sess_out = []
        for s in sessions:
            if s.end is None:
                if s.start >= hi:
                    continue
                sess_out.append({"start": s.start.astimezone(TZ).isoformat(timespec="minutes"),
                                 "end": None, "open": True})
                continue
            if s.end <= lo or s.start >= hi:
                continue
            sess_out.append({"start": s.start.astimezone(TZ).isoformat(timespec="minutes"),
                             "end": s.end.astimezone(TZ).isoformat(timespec="minutes"),
                             "open": False})
        day_out = {}
        emp_abs = absences_by_emp.get(e.id, [])
        employment = ports.employment.employment(eid, period)
        for d in days:
            trow = tabel_rows.get((e.id, d))
            policy = st.day_code_policy.get(trow.code) if trow else None
            window = None
            value = None
            if trow:
                value = (f"{trow.code} {fmt_hours(trow.plan_minutes)}"
                         if policy and policy.carries_hours else trow.code)
                if policy and policy.carries_hours:
                    w = st.windows.get(value)
                    window = [hm(w.start_minute), hm(w.end_minute)] if w else None
            # цвет дня — по смене с ЯКОРЕМ в этом дне: ночная полоса, заходящая
            # на соседний «В», не перекрашивает его код (полоса несёт свой цвет)
            sh_rows = [r for r in shifts_by_emp_day.get((e.id, d.isoformat()), [])
                       if r.date == d]
            shift_hm = None
            if sh_rows:
                s0 = sh_rows[0].start_utc.replace(tzinfo=dt.timezone.utc).astimezone(TZ)
                e0 = sh_rows[0].end_utc.replace(tzinfo=dt.timezone.utc).astimezone(TZ)
                shift_hm = (s0.strftime("%H:%M"), e0.strftime("%H:%M"))
            day_abs = []
            whole_off_color = None
            d_lo = dt.datetime.combine(d, dt.time(0), TZ)
            d_hi = d_lo + dt.timedelta(days=1)
            for a in emp_abs:
                a_lo = a.start_utc.replace(tzinfo=dt.timezone.utc).astimezone(TZ)
                a_hi = a.end_utc.replace(tzinfo=dt.timezone.utc).astimezone(TZ)
                if a_lo < d_hi and a_hi > d_lo:
                    day_abs.append([max(a_lo, d_lo).strftime("%H:%M"),
                                    min(a_hi, d_hi).strftime("%H:%M")])
                    kind = kinds.get(a.kind_id)
                    if (whole_off_color is None and kind is not None and kind.doc_type
                            and covers_window(st, trow, a_lo.date(), a_lo, a_hi)):
                        whole_off_color = kind.color or "#0e9aa7"
            out_of_staff = d < employment.start or (employment.end is not None and d > employment.end)
            day_out[d.isoformat()] = {
                "tabel": value, "window": window, "absences": day_abs,
                "out_of_staff": out_of_staff,
                "color": pick_cell_color(lookups, shift_hm, trow.code if trow else None,
                                         whole_off_color),
            }
        rows.append({"employee": emp_brief(e), "sessions": sess_out, "days": day_out})
    return {"year": year, "month": month, "step_minutes": st.step_minutes,
            "days": [{"date": d.isoformat(), "day": d.day,
                      "weekday": ["пн", "вт", "ср", "чт", "пт", "сб", "вс"][d.weekday()],
                      "is_weekend": d.weekday() >= 5,
                      "is_today": d == now_utc().astimezone(TZ).date()} for d in days],
            "rows": rows}


def _settings_for_period(db, period):
    from ..adapters.sql_settings import SqlSettingsAdapter
    # ConfigError → 422 — централизованный хэндлер main.py (§5.3)
    return SqlSettingsAdapter(db).load(period)


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
        # не HTTP-ошибка: текст дня-карточки в payload вкладки (200 + "error")
        return None, error_text(exc), False
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
    except ValueError as exc:
        # ConfigError/DomainError → централизованный хэндлер main.py (§5.3):
        # текст нарушений конфигурации включает коды CHK-* и место правки.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
