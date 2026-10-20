"""Сериализация доменных результатов в JSON-совместимые структуры (контракт для HTTP
и хранения): глубокая конверсия frozen-dataclass, date/datetime → ISO, read-only
Mapping → dict, tuple → list."""
from __future__ import annotations

import dataclasses
import datetime as dt
from types import MappingProxyType
from typing import Any


def plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: plain(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dt.datetime):
        return value.astimezone(dt.timezone.utc).isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, (dict, MappingProxyType)) or hasattr(value, "items"):
        return {(k.isoformat() if isinstance(k, dt.date) else str(k)): plain(v)
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return value


def result_to_dict(result) -> dict:
    return plain(result)


def flags_to_dict(flags) -> dict:
    return plain(flags)
