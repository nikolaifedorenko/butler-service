"""Единая проверка year/month во всех точках ввода периода.

Проверка — функция, а не ограничение pydantic: она одинаково годится и для параметров
строки запроса (``GET /api/schedule?year=&month=``), и для тела запроса, а отказ имеет
принятый в проекте вид ``{"detail": текст}``. Без неё ``month=13`` доходил до
``calendar.monthrange`` и ``dt.date(...)`` и отдавал клиенту 500.
"""
from __future__ import annotations

from app.core.errors import Validation

PERIOD_DETAIL = "year должен быть 1..9999, month — 1..12"


def ensure_period(year: int, month: int) -> None:
    """Отказ 422, если год и месяц не образуют период."""
    if not (1 <= year <= 9999 and 1 <= month <= 12):
        raise Validation(PERIOD_DETAIL)
