"""Описание документа для выгрузки: абзацы, таблицы, картинки, страница.

Чистые типы: файл (DOCX, PDF) собирает адаптер. Размеры — в миллиметрах, кегль — в пунктах,
цвета — RRGGBB.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Run:
    """Фрагмент текста с одним оформлением. «\\n» в тексте — перенос строки внутри абзаца."""

    text: str = ""
    bold: bool | None = None
    size: float | None = None
    color: str | None = None


@dataclass(frozen=True)
class Paragraph:
    runs: tuple[Run, ...] = ()
    align: str | None = None            # left | center | right
    space_before: float | None = None
    space_after: float | None = None


def text(value: str = "", *, bold: bool | None = None, size: float | None = None, color: str | None = None,
         align: str | None = None, space_before: float | None = None, space_after: float | None = None) -> Paragraph:
    """Абзац из одного фрагмента; пустая строка без оформления — пустой абзац."""
    plain = bold is None and size is None and color is None
    runs = () if not value and plain else (Run(value, bold, size, color),)
    return Paragraph(runs, align, space_before, space_after)


@dataclass(frozen=True)
class Picture:
    """Картинка из файла, уменьшенная для печати. Файла нет или это не картинка —
    вместо неё абзац missing_text."""

    path: str
    width_mm: float
    missing_text: str = ""


@dataclass(frozen=True)
class TCell:
    """Ячейка таблицы: абзацы и картинки подряд."""

    blocks: tuple[Paragraph | Picture, ...] = ()
    fill: str | None = None
    valign: str | None = None           # center


@dataclass
class Table:
    """Таблица с рамкой. widths_mm — ширины колонок; header_rows — сколько первых строк
    повторять на каждой странице; fixed — жёсткая раскладка с узкими полями ячеек (сетки на
    всю ширину листа)."""

    rows: list[list[TCell]]
    widths_mm: tuple[float, ...]
    header_rows: int = 0
    fixed: bool = False


@dataclass(frozen=True)
class Page:
    width_mm: float
    height_mm: float
    margin_x_mm: float
    margin_y_mm: float
    landscape: bool = False


@dataclass(frozen=True)
class Font:
    name: str
    size: float


@dataclass
class Document:
    blocks: list[Paragraph | Table] = field(default_factory=list)
    page: Page | None = None            # None — страница по умолчанию (A4, книжная)
    footer: Paragraph | None = None
    font: Font | None = None            # основной шрифт документа
