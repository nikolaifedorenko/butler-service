"""Публичная поверхность данных модуля stays (граница R3/R4): другие модули импортируют
модели шахматки отсюда, а не из adapters."""
from ..adapters.orm import (  # noqa: F401
    Category,
    CoverageLine,
    Escort,
    Guest,
    Reservation,
    Unit,
)
