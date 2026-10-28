"""Публичная поверхность данных модуля stays (граница R3/R4): другие модули импортируют
модели шахматки отсюда, а не из adapters. Фонд (категории, объекты) — только снимком на
дату: постоянные строки держат лишь id (stays-fund-versions §3.1)."""
from ..adapters.orm import (  # noqa: F401
    CoverageLine,
    Escort,
    Guest,
    Reservation,
)
from .fund_versions import FundSnapshot, fund_on  # noqa: F401
