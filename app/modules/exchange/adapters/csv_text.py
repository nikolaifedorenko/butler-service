"""CSV для Excel: UTF-8 с BOM, разделитель «;»."""
from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from typing import Any

from app.core.format import safe_sheet_cell

from ..domain.tables import Cell


def _value(item: Any) -> Any:
    if isinstance(item, Cell):
        return item.value if item.raw else safe_sheet_cell(item.value)
    return safe_sheet_cell(item)


def write(header: Sequence[str], rows: Iterable[Sequence[Any]], *, delimiter: str = ";") -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=delimiter)
    w.writerow(header)
    for row in rows:
        w.writerow([_value(v) for v in row])
    return ("﻿" + buf.getvalue()).encode("utf-8")
