"""Описание таблицы для выгрузки: листы, строки, ячейки и их оформление.

Чистые типы: формат файла (XLSX, CSV) выбирает вызывающий, записывает адаптер.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Align:
    horizontal: str | None = None       # left | center | right
    vertical: str | None = None         # top | center | bottom
    wrap: bool = False


@dataclass(frozen=True)
class Fill:
    """Сплошная заливка. color и back — RRGGBB; back задают, когда нужны оба цвета узора."""

    color: str
    back: str | None = None


@dataclass(frozen=True)
class Cell:
    """Ячейка с оформлением. Значение без оформления передают как есть, без Cell.

    raw — не защищать строку от запуска как формулы (значение не от пользователя и может
    законно начинаться с «=», «+», «-», «@»). locked — защита ячейки на защищённом листе.
    """

    value: Any = None
    bold: bool = False
    fill: Fill | None = None
    align: Align | None = None
    locked: bool | None = None
    raw: bool = False


def raw(value: Any) -> Cell:
    return Cell(value, raw=True)


@dataclass(frozen=True)
class Column:
    width: float | None = None
    locked: bool | None = None


@dataclass(frozen=True)
class Protect:
    """Защита листа: править можно только незапертые ячейки."""

    allow_format_columns: bool = False
    allow_format_cells: bool = False


@dataclass(frozen=True)
class ListValidation:
    """Выпадающий список: ячейки cells берут варианты из диапазона другого листа."""

    cells: str              # «C2:C20001»
    source_sheet: str
    source_cells: str       # «$A$2:$A$17»


@dataclass
class Sheet:
    """Лист: заголовок в первой строке (строки — полужирным), затем rows подряд.

    Пустая строка в rows оставляет пустую строку листа. Значение None без оформления ячейку
    не создаёт. columns — оформление колонок по номеру с 1.
    """

    title: str
    rows: Iterable[Sequence[Any]] = ()
    header: Sequence[Any] | None = None
    columns: Mapping[int, Column] = field(default_factory=dict)
    freeze: str | None = None           # «A2» — закрепить первую строку
    protect: Protect | None = None
    hidden: bool = False
    validations: Sequence[ListValidation] = ()


class XlsxError(Exception):
    """Файл не принят. kind: too_large | unpacked_too_large | not_xlsx | unreadable."""

    def __init__(self, kind: str):
        self.kind = kind
        super().__init__(kind)
