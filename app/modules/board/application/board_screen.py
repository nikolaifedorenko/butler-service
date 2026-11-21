"""Шахматка батлеров, табло дня и загрузка по дням (§6.2, §6.3).

Шахматка батлеров — только с фамилиями (``stays.view``); табло — на всех уровнях, поля по
уровню видимости (§8). Роутер проверяет право эндпоинта.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.errors import Validation
from app.modules.stays.application.visibility import required_level
from app.modules.stays.ports.duty import DutyPort

from . import boards, views

MAX_DAYS = 62


def butlers_board(db: Session, first: dt.date, last: dt.date, duty: DutyPort) -> dict:
    if last < first or (last - first).days + 1 > MAX_DAYS:
        raise Validation(f"Период — не больше {MAX_DAYS} дней")
    return boards.butlers_board(db, first, last, duty)


def day_board(db: Session, principal: Principal, day: dt.date, f: boards.DayFilters, duty: DutyPort) -> dict:
    out = boards.day_board(db, day, required_level(db, principal), f, duty)
    for key in ("covered", "declined", "need_replacement", "not_required", "special", "uncovered"):
        out["totals"].setdefault(key, None)         # уровню «загрузка» эти итоги не показываются
    return out


def occupancy(db: Session, first: dt.date, last: dt.date, f: views.BoardFilters) -> dict:
    return views.occupancy_grid(db, first, last, f)
