"""Форматы вывода (ядро, R5): защита от CSV/Excel-инъекций, нормализация цветов для
атрибута style, часы для текста документов. Чистые функции без состояния."""
from __future__ import annotations

import re

_HEX_COLOR_RE = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})")


def safe_sheet_cell(value):
    """Защита от CSV/Excel-инъекции формул.

    Ячейка, начинающаяся с «=», «+», «-», «@», TAB или CR, при открытии в Excel/LibreOffice
    может выполниться как формула. Предваряем такие значения апострофом — это общепринятая
    защита (OWASP) от CSV/formula injection.
    """
    if isinstance(value, str) and value and value[0] in "=+-@\t\r":
        return "'" + value
    return value


def normalize_hex_color(value: str | None, default: str) -> str:
    """Цвет только в формате #rgb / #rrggbb (пусто → default), иначе ValueError.

    Цвета попадают во фронтенде в атрибут style="background:…"; произвольная строка
    там — HTML/CSS-инъекция (например, `red"><a href=…>`). Поэтому формат жёсткий.
    """
    v = (value or "").strip()
    if not v:
        return default
    if not _HEX_COLOR_RE.fullmatch(v):
        raise ValueError("Цвет должен быть в формате #RRGGBB (например, #8a94a6)")
    return v.lower()


def hours_text(value: float) -> str:
    """Часы для текста документа: целое без дробной части, иначе с запятой («2», «2,5»)."""
    v = round(float(value or 0), 2)
    return str(int(v)) if abs(v - int(v)) < 1e-9 else f"{v:g}".replace(".", ",")
