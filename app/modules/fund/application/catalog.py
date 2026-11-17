"""Публичная поверхность данных модуля fund (граница R3/R4): другие модули импортируют модели фонда
отсюда, а не из adapters. Постоянные строки держат лишь id; название, категория, этаж и прочее —
в снимках версий (``fund_versions``)."""
from ..adapters.orm import (  # noqa: F401
    Category,
    CategoryKind,
    CategoryState,
    FundGroup,
    FundVersion,
    GroupState,
    Unit,
    UnitFlag,
    UnitLineage,
    UnitState,
    UnitStateFlag,
)
