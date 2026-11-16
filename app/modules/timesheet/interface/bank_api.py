"""API ручных корректировок банка часов сотрудника. Правила — в ``application/bank_entries.py``."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm

from ..application import bank_entries
from ..application.bank_entries import BankAdjustIn
from .schemas import BankAdjustedOut, BankNowOut

router = APIRouter(prefix="/api", tags=["directory"])


@router.post("/employees/{employee_id}/bank-adjust", response_model=BankAdjustedOut)
def bank_adjust(employee_id: int, payload: BankAdjustIn,
                principal: Principal = Depends(require_perm("employees.bank")), db: Session = Depends(get_db)):
    """Ручная корректировка банка часов (+/−) с автором, датой и причиной."""
    return bank_entries.adjust(db, principal, employee_id, payload)


@router.delete("/employees/{employee_id}/bank-adjustments/{adjustment_id}", response_model=BankNowOut)
def bank_adjust_delete(employee_id: int, adjustment_id: int,
                       principal: Principal = Depends(require_perm("employees.bank")), db: Session = Depends(get_db)):
    return {"ok": True, "bank_now": bank_entries.delete_adjustment(db, principal, employee_id, adjustment_id)}
