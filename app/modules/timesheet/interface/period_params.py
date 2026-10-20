"""Единая проверка year/month во всех точках ввода периода (P0-5 ревью 20.10.2026).

Зачем отдельный модуль, а не pydantic-констрейнт
------------------------------------------------
Проверка уже была в пяти роутерах (График, reset-month, УТ, Факт, Табель), но
скопирована текстом и пропущена в шести (continue, copy, clear-month,
fill-from-cycles, reset, modifiers) — там `month=13` долетал до
`calendar.monthrange`/`dt.date(...)` и отдавал клиенту 500.

`pydantic.Field(ge=1, le=12)` закрыл бы только тела запросов (не query-параметры
`GET /api/schedule?year=&month=`) и поменял бы форму ответа на стандартный
fastapi-список ошибок — а контракт проекта везде `{"detail": текст}` (main.py,
§5.3), и `docs/openapi.json` должен остаться без дельты. Поэтому единый помощник
— функция, одинаково пригодная и для query-параметров, и для pydantic-моделей.

Живёт рядом с `formatting.py`, а не в одном из роутеров: роутеры
`timesheet.interface` не импортируют друг друга (контракт
`timesheet-interface-independence` в .importlinter).
"""
from __future__ import annotations

from fastapi import HTTPException

PERIOD_DETAIL = "year должен быть 1..9999, month — 1..12"


def ensure_period(year: int, month: int) -> None:
    """Отказ 422, если год/месяц не образуют период.

    Без проверки `dt.date(year, month, 1)` бросает ValueError, а
    `calendar.monthrange` — IllegalMonthError: обе не маппятся ни одним
    обработчиком main.py и превращаются в 500 на запросе клиента.
    """
    if not (1 <= year <= 9999 and 1 <= month <= 12):
        raise HTTPException(status_code=422, detail=PERIOD_DETAIL)
