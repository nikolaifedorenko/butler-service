"""Справочники фонда (§3.1, §3.5): категории, объекты, метки, настраиваемые поля, список
«Сопровождают гостей» и настройки нагрузки. Ничего не коммитит — commit в роутере."""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.employees.application.catalog import Employee

from ..adapters.orm import (
    Assignment,
    Category,
    CustomField,
    Escort,
    Hold,
    Label,
    Move,
    Reservation,
    StaysSettings,
    Unit,
)

KINDS = {"villa": "вилла", "estate": "имение", "apartment": "апартаменты", "room": "номер"}
FIELD_KINDS = {"text", "choice", "bool", "date"}
FIELD_TARGETS = {"guest", "reservation"}


class FundError(Exception):
    """Ошибка ввода справочника → 422."""


class FundConflict(FundError):
    """Состояние не позволяет операцию (занятый код, есть зависимые записи) → 409."""


def plain(v: Any) -> Any:
    return float(v) if isinstance(v, Decimal) else v


def as_dict(row, fields: tuple[str, ...]) -> dict:
    return {f: plain(getattr(row, f)) for f in fields}


def changes(before: dict, after: dict) -> dict:
    """Разница полей для журнала аудита: {поле: [было, стало]}."""
    return {k: [before.get(k), after.get(k)] for k in after if before.get(k) != after.get(k)}


CATEGORY_FIELDS = ("id", "code", "title", "kind", "escorted", "weight", "sort_order")
UNIT_FIELDS = ("id", "label", "category_id", "building", "floor", "active", "sort_order")
LABEL_FIELDS = ("id", "title", "color")
FIELD_FIELDS = ("id", "target", "code", "title", "kind", "searchable", "sort_order")
SETTINGS_FIELDS = ("vip_bonus", "vvip_bonus", "daily_limit", "replacement_codes")


def field_dict(f: CustomField) -> dict:
    return {**as_dict(f, FIELD_FIELDS), "choices": json.loads(f.choices_json or "[]")}


def _apply(row, data: dict, fields: tuple[str, ...]) -> None:
    for k in fields:
        if k != "id" and k in data:
            setattr(row, k, data[k])


def _update(db: Session, model, rid: int | None, data: dict, fields, not_found: str):
    if rid is None:
        row = model()
        db.add(row)
        before: dict = {}
    else:
        row = db.get(model, rid)
        if row is None:
            raise FundError(not_found)
        before = as_dict(row, fields)
    _apply(row, data, fields)
    db.flush()
    return row, before


def save_category(db: Session, data: dict, cid: int | None) -> tuple[Category, dict]:
    if data["kind"] not in KINDS:
        raise FundError("Неизвестный вид объекта")
    code = data["code"].strip().upper()
    taken = db.scalar(select(Category.id).where(Category.code == code))
    if taken is not None and taken != cid:
        raise FundConflict("Код категории занят")
    return _update(db, Category, cid, {**data, "code": code}, CATEGORY_FIELDS, "Категория не найдена")


def delete_category(db: Session, cid: int) -> dict:
    row = db.get(Category, cid)
    if row is None:
        raise FundError("Категория не найдена")
    if db.scalar(select(Unit.id).where(Unit.category_id == cid).limit(1)) is not None:
        raise FundConflict("В категории есть объекты")
    if db.scalar(select(Reservation.id).where(Reservation.category_id == cid).limit(1)) is not None:
        raise FundConflict("Категория используется в бронях")
    if db.scalar(select(Move.id).where(Move.category_id == cid).limit(1)) is not None:
        raise FundConflict("Категория используется в переездах")
    before = as_dict(row, CATEGORY_FIELDS)
    db.delete(row)
    return before


def save_unit(db: Session, data: dict, uid: int | None) -> tuple[Unit, dict]:
    if db.get(Category, data["category_id"]) is None:
        raise FundError("Категория не найдена")
    label = data["label"].strip()
    if not label:
        raise FundError("Укажите обозначение объекта")
    taken = db.scalar(select(Unit.id).where(Unit.label == label))
    if taken is not None and taken != uid:
        raise FundConflict("Объект с таким обозначением уже есть")
    return _update(db, Unit, uid, {**data, "label": label}, UNIT_FIELDS, "Объект не найден")


def delete_unit(db: Session, uid: int) -> dict:
    row = db.get(Unit, uid)
    if row is None:
        raise FundError("Объект не найден")
    used = (db.scalar(select(Assignment.id).where(Assignment.unit_id == uid).limit(1)) is not None
            or db.scalar(select(Hold.id).where(Hold.unit_id == uid).limit(1)) is not None)
    if used:
        raise FundConflict("У объекта есть брони или блоки — сделайте его неактивным")
    before = as_dict(row, UNIT_FIELDS)
    db.delete(row)
    return before


def save_label(db: Session, data: dict, lid: int | None) -> tuple[Label, dict]:
    title = data["title"].strip()
    taken = db.scalar(select(Label.id).where(Label.title == title))
    if taken is not None and taken != lid:
        raise FundConflict("Метка с таким названием уже есть")
    return _update(db, Label, lid, {**data, "title": title}, LABEL_FIELDS, "Метка не найдена")


def delete_label(db: Session, lid: int) -> dict:
    row = db.get(Label, lid)
    if row is None:
        raise FundError("Метка не найдена")
    if db.scalar(select(Reservation.id).where(Reservation.label_id == lid).limit(1)) is not None:
        raise FundConflict("Метка используется в бронях")
    before = as_dict(row, LABEL_FIELDS)
    db.delete(row)
    return before


def save_field(db: Session, data: dict, fid: int | None) -> tuple[CustomField, dict]:
    if data["target"] not in FIELD_TARGETS:
        raise FundError("Поле относится к гостю или к брони")
    if data["kind"] not in FIELD_KINDS:
        raise FundError("Неизвестный тип поля")
    choices = [c.strip() for c in data.get("choices") or [] if c.strip()]
    if data["kind"] == "choice" and not choices:
        raise FundError("Для списка нужны варианты")
    code = data["code"].strip().lower()
    taken = db.scalar(select(CustomField.id).where(CustomField.target == data["target"],
                                                   CustomField.code == code))
    if taken is not None and taken != fid:
        raise FundConflict("Поле с таким кодом уже есть")
    row, before = _update(db, CustomField, fid, {**data, "code": code}, FIELD_FIELDS,
                          "Поле не найдено")
    if fid is not None:
        before = {**before, "choices": json.loads(row.choices_json or "[]")}
    row.choices_json = json.dumps(choices, ensure_ascii=False)
    return row, before


def delete_field(db: Session, fid: int) -> dict:
    row = db.get(CustomField, fid)
    if row is None:
        raise FundError("Поле не найдено")
    before = field_dict(row)
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


def save_settings(db: Session, vip_bonus: float, vvip_bonus: float, daily_limit: float,
                  replacement_codes: str) -> tuple[StaysSettings, dict]:
    if daily_limit <= 0:
        raise FundError("Лимит нагрузки должен быть больше нуля")
    if vip_bonus < 0 or vvip_bonus < 0:
        raise FundError("Надбавка не может быть отрицательной")
    row = get_settings(db)
    before = as_dict(row, SETTINGS_FIELDS)
    row.vip_bonus, row.vvip_bonus, row.daily_limit = (Decimal(str(v)) for v in
                                                       (vip_bonus, vvip_bonus, daily_limit))
    row.replacement_codes = ",".join(c.strip() for c in replacement_codes.split(",") if c.strip())
    db.flush()
    return row, before


def list_fund(db: Session, with_staff: bool = False) -> dict:
    """with_staff — список активных сотрудников для экрана «Сопровождение» (только stays.setup)."""
    names = dict(db.execute(select(Employee.id, Employee.full_name)).all())
    out = {
        "kinds": [{"code": k, "title": v} for k, v in KINDS.items()],
        "categories": [as_dict(c, CATEGORY_FIELDS) for c in
                       db.scalars(select(Category).order_by(Category.sort_order, Category.code))],
        "units": [as_dict(u, UNIT_FIELDS) for u in
                  db.scalars(select(Unit).order_by(Unit.sort_order, Unit.label))],
        "labels": [as_dict(lb, LABEL_FIELDS) for lb in db.scalars(select(Label).order_by(Label.title))],
        "fields": [field_dict(f) for f in
                   db.scalars(select(CustomField).order_by(CustomField.target, CustomField.sort_order))],
        "escorts": [{"employee_id": e.employee_id, "name": names.get(e.employee_id, ""),
                     "active": e.active} for e in db.scalars(select(Escort))],
        "settings": as_dict(get_settings(db), SETTINGS_FIELDS),
    }
    if with_staff:
        out["staff"] = [{"id": e.id, "name": e.full_name, "position": e.position} for e in
                        db.scalars(select(Employee).where(Employee.active.is_(True))
                                   .order_by(Employee.full_name))]
    return out
