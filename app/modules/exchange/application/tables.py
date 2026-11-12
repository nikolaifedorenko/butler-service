"""Таблицы: запись XLSX и CSV по описанию, чтение XLSX.

Пример:
    write_xlsx([Sheet("Брони", header=["Номер", "Гость"], rows=[["F1", "Иванов"]])])
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from ..adapters import csv_text, xlsx
from ..adapters.xlsx import Reader
from ..domain.tables import (  # noqa: F401 — публичные типы описания таблицы
    Align,
    Cell,
    Column,
    Fill,
    ListValidation,
    Protect,
    Sheet,
    XlsxError,
    raw,
)

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CSV_MEDIA_TYPE = "text/csv; charset=utf-8"


def write_xlsx(sheets: Iterable[Sheet]) -> bytes:
    return xlsx.write(sheets)


def open_xlsx(data: bytes, *, max_bytes: int, max_unpacked_bytes: int) -> Reader:
    return xlsx.open_reader(data, max_bytes=max_bytes, max_unpacked_bytes=max_unpacked_bytes)


def write_csv(header: Sequence[str], rows: Iterable[Sequence[Any]]) -> bytes:
    return csv_text.write(header, rows)


def attachment(filename: str) -> dict[str, str]:
    """Заголовок ответа «скачать как файл»."""
    return {"Content-Disposition": f'attachment; filename="{filename}"'}
