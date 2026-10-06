"""Общие помощники HTTP-слоя для движка: сотрудники периода, порты, ошибки домена → HTTP."""
from __future__ import annotations

import datetime as dt

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..employment import employed_on
from ..groups import group_index, normalize_group
from ..models import Employee, EmploymentPeriod
from ..engine.application.errors import ApplicationError
from ..engine.domain.types.errors import ConfigError, IncompletePeriodError, InvariantViolationError, UnknownDayCodeError

ERROR_TEXTS = {
    "PERIOD_ALREADY_CLOSED": "Период уже закрыт",
    "PERIOD_NOT_CLOSED": "Период не закрыт — пересчитывать нечего",
    "RECALCULATION_FORBIDDEN": "Пересчитать можно только последний закрытый период (следующий уже закрыт)",
}


def period_employees(db: Session, first: dt.date, last: dt.date, ids: list[int] | None = None) -> list[Employee]:
    """Сотрудники, у которых в периоде есть хотя бы один день работы."""
    q = select(Employee).where(Employee.deleted_at.is_(None))
    if ids:
        q = q.where(Employee.id.in_(ids))
    emps = list(db.scalars(q))
    periods: dict[int, list] = {}
    for p in db.scalars(select(EmploymentPeriod).where(EmploymentPeriod.employee_id.in_([e.id for e in emps]))):
        periods.setdefault(p.employee_id, []).append(p)

    def visible(e: Employee) -> bool:
        recs = periods.get(e.id)
        if not recs:
            return e.active
        return any(employed_on(recs, first + dt.timedelta(days=i)) for i in range((last - first).days + 1))

    out = [e for e in emps if visible(e)]
    out.sort(key=lambda e: (group_index(normalize_group(e.schedule_group)), e.full_name))
    return out


def domain_error_text(exc: Exception) -> str:
    if isinstance(exc, ConfigError):
        return "Ошибка настроек: " + "; ".join(f"{c} {dict(d)}" for c, d in exc.violations)
    if isinstance(exc, UnknownDayCodeError):
        return f"Код Табеля «{exc.code}» ({exc.day:%d.%m}) отсутствует в справочнике Т1"
    if isinstance(exc, IncompletePeriodError):
        return f"Период ещё не завершён: закрыть можно с 00:00 {exc.period_end + dt.timedelta(days=1):%d.%m.%Y}"
    if isinstance(exc, InvariantViolationError):
        return f"Внутренняя ошибка расчёта (инвариант {exc.code}) — результат не сохранён"
    if isinstance(exc, ApplicationError):
        return ERROR_TEXTS.get(exc.code, str(exc))
    return str(exc)


def raise_http(exc: Exception) -> None:
    raise HTTPException(status_code=409, detail=domain_error_text(exc))


def emp_brief(e: Employee) -> dict:
    return {"id": e.id, "full_name": e.full_name, "short_name": e.display_name, "position": e.position or "",
            "group": normalize_group(e.schedule_group) or "Другие смены", "color": e.group_color,
            "tab_number": e.tab_number or ""}


def engine_view(db: Session, emp: Employee, day: dt.date):
    """view_period месяца дня (None — если расчёт невозможен: ошибка настроек/Табеля)."""
    from ..engine.adapters.factory import build_ports
    from ..engine.application.periods import month_period
    from ..engine.application.view_period import view_period
    from ..engine.domain.types.errors import DomainError

    try:
        return view_period(str(emp.id), month_period(day.year, day.month), build_ports(db))
    except DomainError:
        return None


def bank_now(db: Session, emp: Employee, day: dt.date) -> float:
    """Предварительный банк часов (view текущего месяца, без изъятий), в часах."""
    view = engine_view(db, emp, day)
    return round(view.settle.bank_closed_minutes / 60, 2) if view else 0.0


def day_summary(db: Session, emp: Employee, day: dt.date) -> dict:
    """Карточка дня из движка v4 для экранов отметок."""
    view = engine_view(db, emp, day)
    card = next((c for c in view.settle.cards if c.day == day), None) if view else None
    if card is None:
        return {"planned_hours": 0.0, "fact_hours": 0.0, "night_hours": 0.0, "ot_hours": 0.0,
                "deficit_hours": 0.0, "status": "", "flags": [], "value": ""}
    night = sum(m for t, m in card.codes.items() if t.startswith("ДН"))
    return {"planned_hours": card.plan_minutes / 60, "fact_hours": card.full_fact_minutes / 60,
            "night_hours": night / 60, "ot_hours": card.overtime_minutes / 60,
            "deficit_hours": card.debt_minutes / 60, "value": card.timesheet_value,
            "status": next((f.code for f in view.flags_of(day)), ""),
            "flags": [f.code for f in view.flags_of(day)]}
