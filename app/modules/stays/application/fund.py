"""Общее для фонда и всего, что выше: ошибки ввода и конфликта состояния, разница полей для
журнала аудита и запись строки справочника. Категории и объекты — версиями с даты: читаются
через fund_versions, пишутся через fund_drafts."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import Validation


class FundError(Validation):
    """Ошибка ввода справочника → 422. Остальные отказы шахматки — её наследники со своим статусом."""


class FundConflict(FundError):
    """Состояние не позволяет операцию (занятый код, есть зависимые записи) → 409."""

    status_code = 409


def plain(v: Any) -> Any:
    return float(v) if isinstance(v, Decimal) else v


def as_dict(row, fields: tuple[str, ...]) -> dict:
    return {f: plain(getattr(row, f)) for f in fields}


def changes(before: dict, after: dict) -> dict:
    """Разница полей для журнала аудита: {поле: [было, стало]}."""
    return {k: [before.get(k), after.get(k)] for k in after if before.get(k) != after.get(k)}


def apply_fields(row, data: dict, fields: tuple[str, ...]) -> None:
    for k in fields:
        if k != "id" and k in data:
            setattr(row, k, data[k])


def upsert_row(db: Session, model, rid: int | None, data: dict, fields, not_found: str):
    if rid is None:
        row = model()
        db.add(row)
        before: dict = {}
    else:
        row = db.get(model, rid)
        if row is None:
            raise FundError(not_found)
        before = as_dict(row, fields)
    apply_fields(row, data, fields)
    db.flush()
    return row, before
