"""Вкладка «Брони» (спецификация фонда по версиям §8): список бронирований и его выгрузка в Excel.

Только уровни «с фамилиями» и «полный»: список без фамилий бесполезен и сам по себе оракул.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import transactional
from app.core.errors import Forbidden
from app.modules.stays.application.visibility import Level, level_for

from . import bookings
from .export import bookings_xlsx


def _access(db: Session, principal: Principal) -> Level:
    level = level_for(db, principal)
    if level is None or level == "occupancy":
        raise Forbidden("Список броней доступен с правом «Шахматки с фамилиями»")
    return level


def list_bookings(db: Session, principal: Principal, query: bookings.BookingQuery) -> dict:
    return bookings.list_bookings(db, query, _access(db, principal))


@transactional
def export(db: Session, principal: Principal, query: bookings.BookingQuery) -> tuple[bytes, str]:
    """Выгрузка в Excel: содержимое и имя файла; выгрузка записывается в журнал аудита."""
    rows = bookings.find_bookings(db, query, _access(db, principal))
    f = query.filters
    audit(db, principal, "stays_export", "export:bookings", {
        "kind": "bookings", "first": query.first.isoformat(), "last": query.last.isoformat(), "mode": query.mode,
        "sort": query.sort, "dir": query.dir, "rows": len(rows), "statuses": list(query.statuses),
        "label_ids": list(query.label_ids), "unassigned": query.unassigned, "with_warnings": query.with_warnings,
        "group_ids": list(f.group_ids), "category_ids": list(f.category_ids), "flag_ids": list(f.flag_ids),
        "kind_ids": list(f.kind_ids), "floor": f.floor, "escorted": f.escorted_only, "special": f.special,
        "vip_code_ids": list(f.vip_code_ids),
        "employee_id": f.employee_id, "q": f.q})
    return bookings_xlsx(rows), f"bookings_{query.first.isoformat()}_{query.last.isoformat()}.xlsx"
