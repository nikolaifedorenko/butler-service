"""Ручные корректировки банка часов сотрудника: добавить (+/−) с причиной и отменить."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import lock_employee, transactional
from app.core.errors import NotFound, Validation
from app.core.time import local_date, now
from app.modules.people.application import Employee

from ..adapters.orm import BankAdjustment
from . import bank_adjustment
from .dates import parse_date
from .employee_card import adjustment_dict, bank_as_of
from .engine_common import engine_ports, now_utc


def _author_name(principal: Principal) -> str:
    if principal.employee:
        return principal.employee.display_name
    return principal.user.username


class BankAdjustIn(BaseModel):
    hours: float                   # со знаком: +4 добавить, -8 списать
    date: Optional[str] = None     # с какой даты учитывается (по умолчанию сегодня)
    note: str = ""                 # «почему» — обязательное пояснение
    reason_code: str = "manual"    # "OPENING_SEED" — посев начального банка (v7.1/R37)


@transactional
def adjust(db: Session, principal: Principal, employee_id: int, payload: BankAdjustIn) -> dict:
    """Ручная корректировка банка часов (+/−) с автором, датой и причиной."""
    emp = db.get(Employee, employee_id)
    if not emp:
        raise NotFound("Сотрудник не найден")
    hours = round(payload.hours, 2)
    seed = (payload.reason_code or "manual").strip() == "OPENING_SEED"
    if hours == 0 and not seed:
        raise Validation("Часы корректировки не могут быть нулевыми")
    if not payload.note.strip():
        raise Validation("Укажите причину корректировки — она попадёт в историю")
    eff = parse_date(payload.date) or local_date()
    # точка ввода корректировок (7.2, v7.1/R37): посев — только первый период;
    # закрытый период — только через пересчёт
    # отказ (ApplicationError) общий обработчик переводит в 409
    bank_adjustment.validate_adjustment_entry(str(emp.id), eff,
                                              payload.reason_code or "manual",
                                              engine_ports(db, principal, now_utc()))
    lock_employee(db, emp.id)            # корректировка — вход закрытия периода (TOCTOU)
    adj = BankAdjustment(employee_id=emp.id, hours=hours, effective_date=eff,
                         note=payload.note.strip(), reason_code=(payload.reason_code or "manual"),
                         author_id=principal.user.id,
                         author_name=_author_name(principal), created_at=now())
    db.add(adj)
    audit(db, principal, "bank_adjust", f"employee:{emp.id}",
          {"hours": hours, "date": eff.isoformat(), "note": adj.note})
    db.flush()      # номер корректировки нужен ответу
    return {"ok": True, "adjustment": adjustment_dict(adj),
            "bank_now": bank_as_of(db, emp)}


@transactional
def delete_adjustment(db: Session, principal: Principal, employee_id: int, adjustment_id: int) -> float:
    """Отменить корректировку. Возвращает банк сотрудника после отмены."""
    adj = db.get(BankAdjustment, adjustment_id)
    if not adj or adj.employee_id != employee_id:
        raise NotFound("Корректировка не найдена")
    data = adjustment_dict(adj)
    lock_employee(db, employee_id)
    db.delete(adj)
    audit(db, principal, "bank_adjust_delete", f"employee:{employee_id}", data)
    db.flush()
    emp = db.get(Employee, employee_id)
    return bank_as_of(db, emp) if emp else 0.0
