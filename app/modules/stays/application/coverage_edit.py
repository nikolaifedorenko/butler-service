"""Покрытие батлерами (§4.2, §4.5, §5): шаблоны, правка по дням, подбор и подмена, «добавить смену
в График». Изменяющие операции — с предпросмотром (§4.6). Роутер проверяет право эндпоинта
(``stays.assign``; чтение — ``stays.assign`` или ``stays.view``).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import transactional
from app.core.errors import Validation
from app.core.permissions import principal_permissions

from ..adapters.orm import CoverageLine
from ..ports.duty import DutyPort
from . import coverage
from .coverage import Scope
from .coverage_forms import MAX_DAYS, AddShiftIn, DayIn, DaysIn, ScopeIn, TemplateIn
from .previewed import run_previewed


def _span(first: dt.date, last: dt.date) -> None:
    if last < first or (last - first).days + 1 > MAX_DAYS:
        raise Validation(f"Период — не больше {MAX_DAYS} дней")


def _target(p: ScopeIn) -> str:
    return f"reservation:{p.reservation_id}" if p.reservation_id else f"group:{p.group_id}"


def _may_overbook(principal: Principal) -> bool:
    return "stays.overbook" in principal.gate_permissions


def template(db: Session, principal: Principal, payload: TemplateIn, *, preview_only: bool,
             duty: DutyPort) -> dict:
    _span(payload.first, payload.last)

    def operation():
        plan = coverage.apply_template(db, payload.scope(), payload.kind, payload.butlers, payload.first,
                                       payload.last, payload.replace, duty)
        audit(db, principal, "stays_coverage", _target(payload),
              {"template": payload.kind, "butlers": payload.butlers, "replace": payload.replace,
               "guest_ids": payload.guest_ids, "days": [[d.isoformat(), e] for d, e in plan]})
        return {"written": len(plan)}
    return run_previewed(db, operation, preview_only=preview_only, may_overbook=_may_overbook(principal),
                         window=(payload.first, payload.last), duty=duty)


def set_day(db: Session, principal: Principal, payload: DayIn, *, preview_only: bool, duty: DutyPort) -> dict:
    def operation():
        row = coverage.set_day(db, payload.scope(), payload.day, payload.employee_id, payload.overnight,
                               payload.comment)
        audit(db, principal, "stays_coverage", _target(payload),
              {"day": payload.day.isoformat(), "employee_id": payload.employee_id, "guest_ids": payload.guest_ids})
        return {"line_id": row.id if row else None}
    return run_previewed(db, operation, preview_only=preview_only, may_overbook=_may_overbook(principal),
                         window=(payload.day, payload.day), duty=duty)


def set_days(db: Session, principal: Principal, payload: DaysIn, *, preview_only: bool, duty: DutyPort) -> dict:
    """Назначение по дням (§6 «по дням»): одна операция, один предпросмотр."""
    days = [(x.day, x.employee_id) for x in payload.days]

    def operation():
        n = coverage.set_days(db, payload.scope(), days)
        audit(db, principal, "stays_coverage", _target(payload),
              {"days": [[d.isoformat(), e] for d, e in days], "guest_ids": payload.guest_ids})
        return {"written": n}
    return run_previewed(db, operation, preview_only=preview_only, may_overbook=_may_overbook(principal),
                         window=(min(d for d, _ in days), max(d for d, _ in days)), duty=duty)


def remove_line(db: Session, principal: Principal, line_id: int, *, preview_only: bool, duty: DutyPort) -> dict:
    row = db.get(CoverageLine, line_id)
    window = (row.day, row.day) if row else None

    def operation():
        gone = coverage.delete_line(db, line_id)
        target = f"reservation:{gone.reservation_id}" if gone.reservation_id else f"group:{gone.group_id}"
        audit(db, principal, "stays_coverage", target,
              {"removed": {"day": gone.day.isoformat(), "employee_id": gone.employee_id, "line_id": line_id}})
        return {"ok": True}
    return run_previewed(db, operation, preview_only=preview_only, may_overbook=_may_overbook(principal),
                         window=window, duty=duty)


def _ids(raw: str) -> list[int]:
    try:
        return [int(x) for x in raw.split(",") if x.strip()]
    except ValueError:
        raise Validation("Гости — номера через запятую") from None


def candidates(db: Session, day: dt.date, reservation_id: int | None, group_id: int | None, guest_ids: str,
               duty: DutyPort) -> list[dict]:
    """Подбор батлеров на день: нагрузка, «знает гостя», «то же место»."""
    return coverage.candidates(db, day, Scope(reservation_id, group_id, frozenset(_ids(guest_ids))), duty)


def replacements(db: Session, first: dt.date, last: dt.date, duty: DutyPort) -> list[dict]:
    _span(first, last)
    return coverage.replacement_list(db, first, last, duty)


@transactional
def add_shift(db: Session, principal: Principal, payload: AddShiftIn) -> dict:
    """Смена Графика для батлера «вне смены»: два права, две записи журнала (§5)."""
    shifts = coverage.add_shift(db, principal_permissions(db, principal), payload.employee_id, payload.day,
                                payload.shift_type_id, principal)
    intervals = [[s.start_utc.isoformat(), s.end_utc.isoformat()] for s in shifts]
    audit(db, principal, "schedule_manual_shift", f"employee:{payload.employee_id}",
          {"date": payload.day.isoformat(), "shift_type_id": payload.shift_type_id, "shifts": intervals,
           "via": "stays"})
    audit(db, principal, "stays_add_shift", f"employee:{payload.employee_id}",
          {"date": payload.day.isoformat(), "shift_type_id": payload.shift_type_id})
    return {"ok": True}
