"""Снимки словаря смен: «как смена выглядела в конкретный день».

Зачем: словарь смен редактируют (добавили 10:00–22:00, поработали месяц, удалили).
Отработанные смены в прошлом при этом НЕ должны меняться и не должны ломаться:
  * удаление смены = архивация (active=False, archived_at), строка остаётся в БД;
  * изменение времени/названия создаёт ревизию ShiftRevision: прошлые даты берут
    прежние значения, новые — текущие.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .deps import local_date
from .models import ShiftRevision, ShiftType

REV_FIELDS = ("code", "name", "display_code", "tzh_code", "kind", "start_time", "end_time",
              "overnight", "color", "is_working", "counts_as_worked", "is_default_off",
              "deduct_from_bank", "doc_type")

EPOCH = dt.date(2000, 1, 1)      # «значения действовали с начала времён»


def planned_hours_of(start_time: str, end_time: str, kind: str = "work") -> float:
    if kind != "work" or not start_time or not end_time:
        return 0.0
    try:
        h1, m1 = (int(x) for x in start_time.split(":"))
        h2, m2 = (int(x) for x in end_time.split(":"))
    except ValueError:
        return 0.0
    mins = (h2 * 60 + m2) - (h1 * 60 + m1)
    if mins <= 0:
        mins += 24 * 60
    return round(max(0.0, mins / 60.0), 2)


class ShiftView:
    """Смена или её исторический снимок. Интерфейс совпадает с ShiftType,
    поэтому существующий код расчёта и отрисовки работает без изменений."""

    __slots__ = ("id", "active", "sort_order", "archived_at", "is_revision", "revision_from",
                 "punch_in_allowed", "punch_out_allowed") + REV_FIELDS

    def __init__(self, shift: ShiftType, values: Optional[dict] = None,
                 revision_from: Optional[dt.date] = None):
        self.id = shift.id
        self.active = shift.active
        self.sort_order = shift.sort_order
        self.archived_at = shift.archived_at
        self.is_revision = values is not None
        self.revision_from = revision_from
        # флаги «можно ли отмечаться» в ревизиях не хранятся: действуют текущие значения
        self.punch_in_allowed = bool(getattr(shift, "punch_in_allowed", True))
        self.punch_out_allowed = bool(getattr(shift, "punch_out_allowed", True))
        for f in REV_FIELDS:
            setattr(self, f, values[f] if values else getattr(shift, f))

    @property
    def planned_hours(self) -> float:
        return planned_hours_of(self.start_time, self.end_time, self.kind)

    @property
    def is_archived(self) -> bool:
        return bool(self.archived_at) or not self.active

    def brief(self) -> dict:
        return {
            "id": self.id, "code": self.code, "name": self.name, "kind": self.kind,
            "color": self.color, "display_code": self.display_code, "tzh_code": self.tzh_code,
            "start": self.start_time, "end": self.end_time, "overnight": self.overnight,
            "planned_hours": self.planned_hours, "is_default_off": self.is_default_off,
            "doc_type": self.doc_type or "", "deduct_from_bank": bool(self.deduct_from_bank),
            "archived": self.is_archived, "historical": self.is_revision,
        }

    def __repr__(self) -> str:  # pragma: no cover - отладка
        return f"<ShiftView {self.code} {self.start_time}-{self.end_time}{' (историческая)' if self.is_revision else ''}>"


def view_at(db: Session, shift: Optional[ShiftType], date: dt.date) -> Optional[ShiftView]:
    """Смена такой, какой она была в дату `date` (по ревизиям словаря)."""
    if shift is None:
        return None
    rev = db.scalar(select(ShiftRevision).where(
        ShiftRevision.shift_type_id == shift.id,
        ShiftRevision.valid_from <= date).order_by(ShiftRevision.valid_from.desc()).limit(1))
    if rev is None:
        return ShiftView(shift)
    values = {f: getattr(rev, f) for f in REV_FIELDS}
    return ShiftView(shift, values, revision_from=rev.valid_from)


def freeze_before_update(db: Session, shift: ShiftType, effective_from: dt.date) -> None:
    """Зафиксировать текущие значения смены как действующие в прошлом,
    чтобы предстоящее изменение не переписало историю."""
    existing = db.scalar(select(ShiftRevision).where(
        ShiftRevision.shift_type_id == shift.id).limit(1))
    if existing is None:
        db.add(ShiftRevision(shift_type_id=shift.id, valid_from=EPOCH,
                             **{f: getattr(shift, f) for f in REV_FIELDS}))
    db.flush()


def add_revision(db: Session, shift: ShiftType, effective_from: dt.date) -> ShiftRevision:
    """Записать новые значения смены, действующие с `effective_from`."""
    rev = ShiftRevision(shift_type_id=shift.id, valid_from=effective_from,
                        **{f: getattr(shift, f) for f in REV_FIELDS})
    db.add(rev)
    db.flush()
    return rev


def find_by_code(db: Session, code: str) -> Optional[ShiftType]:
    """Поиск смены по коду — включая архивные (нужны для прошлых графиков)."""
    if not code:
        return None
    return db.scalar(select(ShiftType).where(ShiftType.code == code))


def archive_shift(db: Session, shift: ShiftType) -> None:
    """«Удаление» смены из словаря = архивация: прошлые ячейки продолжают считаться."""
    freeze_before_update(db, shift, local_date())
    shift.active = False
    shift.archived_at = local_date()
    db.flush()
