"""Глубокая неизменяемость коллекций (2.5).

`frozen=True` запрещает замену поля, но не защищает содержимое коллекций;
поэтому `Mapping`-поля материализуются как read-only представление
(`types.MappingProxyType`) по копии исходного словаря, последовательности —
как `tuple`, а значения `DataValue` нормализуются рекурсивно.
"""
from __future__ import annotations

import datetime as dt
from types import MappingProxyType
from typing import Any, Mapping


def freeze_mapping(value: Mapping | None) -> Mapping:
    """Read-only `Mapping` по копии словаря (2.5)."""
    return MappingProxyType(dict(value or {}))


def freeze_nested_mapping(value: Mapping | None) -> Mapping:
    """Двухуровневый read-only `Mapping` (для `mgmt_timesheet`, 3.2)."""
    return MappingProxyType({k: MappingProxyType(dict(v)) for k, v in (value or {}).items()})


def freeze_data_value(value: Any) -> Any:
    """Рекурсивная нормализация `DataValue` (3.1): dict → read-only, list → tuple."""
    if isinstance(value, Mapping):
        return MappingProxyType({k: freeze_data_value(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze_data_value(v) for v in value)
    if isinstance(value, (bool, int, float, str, dt.date, dt.datetime)) or value is None:
        return value
    raise TypeError(f"invalid DataValue type: {type(value).__name__}")


def freeze_data(value: Mapping | None) -> Mapping:
    """`Reason.data` / `Flag.data`: ровно ключи реестра, значения — `DataValue` (3.4)."""
    return MappingProxyType({k: freeze_data_value(v) for k, v in (value or {}).items()})


def freeze_mapping_of_minutes(value: Mapping | None) -> Mapping:
    """`DayCard.codes`: read-only по копии (2.5)."""
    return MappingProxyType({k: int(v) for k, v in (value or {}).items()})
