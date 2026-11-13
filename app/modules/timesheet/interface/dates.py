"""Разбор дат из тела запроса."""
from __future__ import annotations

import datetime as dt
from typing import Optional

from app.core.errors import Validation


def parse_date(value: Optional[str]) -> Optional[dt.date]:
    """Дата ГГГГ-ММ-ДД или None для пустого значения; иное — ошибка 422."""
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise Validation("Дата должна быть в формате ГГГГ-ММ-ДД")
