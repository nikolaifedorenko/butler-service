"""Табельная часть карточки сотрудника: банк часов, блоки графика, значение рабочего дня.

Карточку показывает модуль employees; что относится к Табелю и Графику, считает этот файл.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import local_date

from .base_schedule import load_base_config, parse_pattern, pattern_for_date, validate_pattern_label
from .catalog import BankAdjustment, BlockAssignment
from .engine_common import last_closed_bank


def adjustment_dict(a: BankAdjustment) -> dict:
    return {"id": a.id, "hours": a.hours, "date": a.effective_date.isoformat(),
            "note": a.note or "", "author": a.author_name or "",
            "reason_code": a.reason_code or "",
            "created_at": a.created_at.isoformat(timespec="minutes") if a.created_at else ""}


def bank_as_of(db: Session, emp) -> float:
    """Банк = итог последнего ЗАКРЫТОГО периода (чтение из хранилища без домена,
    RUL-CLOSED-PERIOD-IMMUTABLE); «живой» предварительный банк — в Управленческом табеле."""
    hours, _period = last_closed_bank(db, emp.id)
    return hours if hours is not None else 0.0


def _block_label(b: BlockAssignment) -> str:
    pat = parse_pattern(b.pattern_json)
    if not pat:
        return ""
    try:
        return validate_pattern_label(pat)
    except ValueError:
        return ""


def current_value(db: Session, emp) -> str:
    """Значение рабочего дня сотрудника на сегодня: своё из истории переводов либо значение
    блока из настроек объекта."""
    try:
        pat = pattern_for_date(db, emp, local_date(), cfg=load_base_config(db))
        return (pat.get("value") or "").strip()
    except Exception:
        return ""


def history(db: Session, emp) -> dict:
    """Блоки графика с датами, значение рабочего дня, корректировки банка и банк на сегодня."""
    blocks = db.scalars(select(BlockAssignment).where(BlockAssignment.employee_id == emp.id)
                        .order_by(BlockAssignment.start_date)).all()
    adjustments = db.scalars(select(BankAdjustment).where(
        BankAdjustment.employee_id == emp.id).order_by(
        BankAdjustment.effective_date.desc(), BankAdjustment.id.desc())).all()
    return {
        "blocks": [{"group": b.group, "start": b.start_date.isoformat(),
                    "end": b.end_date.isoformat() if b.end_date else None,
                    "pattern_label": _block_label(b)} for b in blocks],
        "current_value": current_value(db, emp),
        "bank_adjustments": [adjustment_dict(a) for a in adjustments],
        "bank_now": bank_as_of(db, emp),
    }
