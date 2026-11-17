"""Справочники брони: метки, список «Сопровождают гостей», настройки нагрузки (§3.1, §3.5).

Категории и объекты — версиями фонда (``fund_versions``/``fund_drafts``), настраиваемые поля и
VIP-коды — у гостей. Здесь то, что принадлежит броням. Ничего не коммитит.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.fund.application.fund import FundConflict, FundError, as_dict, upsert_row
from app.modules.guests.application.catalog import CustomField
from app.modules.guests.application.guest_fields import field_dict
from app.modules.people.application.catalog import Employee

from ..adapters.orm import Escort, Label, Reservation, StaysSettings

LABEL_FIELDS = ("id", "title", "color")
SETTINGS_FIELDS = ("special_factor", "daily_limit", "replacement_codes")


def save_label(db: Session, data: dict, lid: int | None) -> tuple[Label, dict]:
    title = data["title"].strip()
    taken = db.scalar(select(Label.id).where(Label.title == title))
    if taken is not None and taken != lid:
        raise FundConflict("Метка с таким названием уже есть")
    return upsert_row(db, Label, lid, {**data, "title": title}, LABEL_FIELDS, "Метка не найдена")


def delete_label(db: Session, lid: int) -> dict:
    row = db.get(Label, lid)
    if row is None:
        raise FundError("Метка не найдена")
    if db.scalar(select(Reservation.id).where(Reservation.label_id == lid).limit(1)) is not None:
        raise FundConflict("Метка используется в бронях")
    before = as_dict(row, LABEL_FIELDS)
    db.delete(row)
    return before


def set_escort(db: Session, employee_id: int, active: bool) -> Escort:
    if db.get(Employee, employee_id) is None:
        raise FundError("Сотрудник не найден")
    row = db.scalar(select(Escort).where(Escort.employee_id == employee_id))
    if row is None:
        row = Escort(employee_id=employee_id)
        db.add(row)
    row.active = active
    db.flush()
    return row


def seed_escorts_from_positions(db: Session, position: str = "батлер") -> int:
    """Первичное заполнение: активные сотрудники, в должности которых есть position (§3.4)."""
    have = set(db.scalars(select(Escort.employee_id)))
    # фильтр в Python: SQLite lower() кириллицу не понижает, а сотрудников — десятки
    added = [e for e in db.scalars(select(Employee).where(Employee.active.is_(True)))
             if position.lower() in e.position.lower() and e.id not in have]
    db.add_all(Escort(employee_id=e.id, active=True) for e in added)
    db.flush()
    return len(added)


def get_settings(db: Session) -> StaysSettings:
    row = db.get(StaysSettings, 1)
    if row is None:                 # строку заводит ревизия 0008; страховка для пустых тестовых схем
        row = StaysSettings(id=1)
        db.add(row)
        db.flush()
    return row


def save_settings(db: Session, special_factor: float | None, daily_limit: float,
                  replacement_codes: str) -> tuple[StaysSettings, dict]:
    """special_factor не задан (None) — остаётся прежним."""
    if daily_limit <= 0:
        raise FundError("Лимит нагрузки должен быть больше нуля")
    if special_factor is not None and not 0.1 <= special_factor <= 99:
        raise FundError("Коэффициент особого гостя — число от 0,1 до 99")
    row = get_settings(db)
    before = as_dict(row, SETTINGS_FIELDS)
    row.daily_limit = Decimal(str(daily_limit))
    if special_factor is not None:
        row.special_factor = Decimal(str(special_factor)).quantize(Decimal('0.01'))
    row.replacement_codes = ",".join(c.strip() for c in replacement_codes.split(",") if c.strip())
    db.flush()
    return row, before


def list_fund(db: Session, with_staff: bool = False) -> dict:
    """with_staff — список активных сотрудников для экрана «Сопровождение» (только stays.setup).
    Категории, объекты, флаги и виды — в GET /fund/snapshot (фонд на дату)."""
    names = dict(db.execute(select(Employee.id, Employee.full_name)).all())
    out = {
        "labels": [as_dict(lb, LABEL_FIELDS) for lb in db.scalars(select(Label).order_by(Label.title))],
        "fields": [field_dict(f) for f in
                   db.scalars(select(CustomField).order_by(CustomField.target, CustomField.sort_order))],
        "escorts": [{"employee_id": e.employee_id, "name": names.get(e.employee_id, ""),
                     "active": e.active} for e in db.scalars(select(Escort))],
        "settings": as_dict(get_settings(db), SETTINGS_FIELDS),
        # «Шахматка в эксплуатации» (§9.3): включён — начальной загрузки нет
        "in_production": bool(get_settings(db).in_production),
    }
    if with_staff:
        out["staff"] = [{"id": e.id, "name": e.full_name, "position": e.position} for e in
                        db.scalars(select(Employee).where(Employee.active.is_(True))
                                   .order_by(Employee.full_name))]
    return out
