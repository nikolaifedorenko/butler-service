"""Настраиваемые поля гостя и брони (§3.1): определения. Значения хранят профиль и бронь."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..adapters.orm import CustomField
from .fund import FundConflict, FundError, as_dict, upsert_row

FIELD_KINDS = {"text", "choice", "bool", "date"}
FIELD_TARGETS = {"guest", "reservation"}
FIELD_FIELDS = ("id", "target", "code", "title", "kind", "searchable", "sort_order")


def field_dict(f: CustomField) -> dict:
    return {**as_dict(f, FIELD_FIELDS), "choices": f.choices}


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
    row, before = upsert_row(db, CustomField, fid, {**data, "code": code}, FIELD_FIELDS,
                          "Поле не найдено")
    if fid is not None:
        before = {**before, "choices": row.choices}
    row.choices = choices
    return row, before


def delete_field(db: Session, fid: int) -> dict:
    row = db.get(CustomField, fid)
    if row is None:
        raise FundError("Поле не найдено")
    before = field_dict(row)
    db.delete(row)
    return before
