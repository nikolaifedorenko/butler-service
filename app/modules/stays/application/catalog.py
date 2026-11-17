"""Публичная поверхность данных модуля stays (граница R3/R4): другие модули импортируют модели
шахматки отсюда, а не из adapters. Фонд и гости — в своих модулях (``fund``, ``guests``)."""
from ..adapters.orm import (  # noqa: F401
    Assignment,
    Block,
    BlockNight,
    Companion,
    CoverageGuest,
    CoverageLine,
    Escort,
    Label,
    Logistics,
    Move,
    Occupant,
    Ooo,
    Reservation,
    StayGroup,
    StaysSettings,
)
