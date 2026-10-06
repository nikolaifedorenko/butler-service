"""Сериализация результатов движка в JSON-совместимые структуры (контракт для HTTP и хранения)."""
from __future__ import annotations

import dataclasses
import datetime as dt
from typing import Any

from ..domain.types.results import FlagsResult, SettleResult


def plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {f.name: plain(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, dict) or hasattr(value, "items"):
        return {(k.isoformat() if isinstance(k, dt.date) else k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return value


def result_to_dict(result: SettleResult) -> dict:
    return plain(result)


def flags_to_list(flags: FlagsResult) -> list:
    return plain(flags.flags)
