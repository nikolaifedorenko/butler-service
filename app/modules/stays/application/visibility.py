"""Уровни видимости персональных данных гостей (§8). Сервер не отдаёт поля, которые уровню
не положены: фильтрация — здесь, в сериализаторах, а не в интерфейсе.

* occupancy — занятость: объекты, даты, статусы, РЗ/ПВ, число гостей; ни фамилий, ни
  уровня, ни номера брони, ни метки;
* names — для работы службы: + номер брони, метка, короткое имя главного гостя, VIP-уровень;
* full — + заказчик, повод, примечания, отказ от батлера, настраиваемые поля, логистика.
"""
from __future__ import annotations

from typing import Literal

from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.permissions import principal_permissions

Level = Literal["occupancy", "names", "full"]
LEVEL_ORDER = {"occupancy": 0, "names": 1, "full": 2}
OCCUPANCY_BAR = ("reservation_id", "seg_index", "unit_id", "category_id", "status", "start", "end",
                 "start_pos", "end_pos", "early", "late", "guests_count")
NAMES_BAR = (*OCCUPANCY_BAR, "number", "label", "main_guest", "mains", "level", "butlers_today")
FULL_BAR = (*NAMES_BAR, "customer", "purpose", "paid_by", "note", "declined_butler", "fields")
BAR_FIELDS = {"occupancy": OCCUPANCY_BAR, "names": NAMES_BAR, "full": FULL_BAR}


def level_for(db: Session, principal: Principal) -> Level | None:
    # гейт require_perm этого запроса уже вычислил права — повторно не запрашиваем
    perms = getattr(principal, "gate_permissions", None) or principal_permissions(db, principal)
    if "stays.guests" in perms and "stays.view" in perms:
        return "full"
    if "stays.view" in perms:
        return "names"
    if "stays.occupancy" in perms:
        return "occupancy"
    return None


def at_least(level: Level | None, needed: Level) -> bool:
    return level is not None and LEVEL_ORDER[level] >= LEVEL_ORDER[needed]


def cut(data: dict, fields: tuple[str, ...]) -> dict:
    return {k: data[k] for k in fields if k in data}


def serialize_bar(bar: dict, level: Level) -> dict:
    return cut(bar, BAR_FIELDS[level])
