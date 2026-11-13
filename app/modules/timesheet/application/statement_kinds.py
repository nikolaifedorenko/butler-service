"""Виды заявлений — порт Графика: какие заявления существуют, знает модуль заявлений.

Поиск подключает composition root (bootstrap/registry.wire): табель не импортирует модули
над собой (ADR-0013, раздел 5).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

_lookup: Callable[[Any, str], bool] | None = None


def set_lookup(fn: Callable[[Any, str], bool]) -> None:
    """fn(db, code) -> существует ли вид заявления с таким кодом."""
    global _lookup
    _lookup = fn


def statement_kind_exists(db, code: str) -> bool:
    if _lookup is None:
        raise RuntimeError("Поиск видов заявлений не подключён: вызовите bootstrap.registry.wire()")
    return _lookup(db, code)
