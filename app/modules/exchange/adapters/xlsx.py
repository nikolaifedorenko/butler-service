"""XLSX на openpyxl: запись листов по описанию и чтение значений."""
from __future__ import annotations

import io
import zipfile
from collections.abc import Iterable, Iterator
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill, Protection
from openpyxl.utils import get_column_letter, quote_sheetname
from openpyxl.worksheet.datavalidation import DataValidation

from app.core.format import safe_sheet_cell

from ..domain.tables import Align, Cell, Fill, Sheet, XlsxError

_BOLD = Font(bold=True)


def clean(value: Any, *, guard: bool = True) -> Any:
    """Строка, пригодная для ячейки: без управляющих символов (их формат не допускает) и,
    если guard, с защитой от запуска как формулы."""
    if not isinstance(value, str):
        return value
    value = ILLEGAL_CHARACTERS_RE.sub("", value)
    return safe_sheet_cell(value) if guard else value


class _Styles:
    """Объекты оформления создаются один раз на значение."""

    def __init__(self) -> None:
        self._fills: dict[Fill, PatternFill] = {}
        self._aligns: dict[Align, Alignment] = {}
        self._locks = {True: Protection(locked=True), False: Protection(locked=False)}

    def fill(self, f: Fill) -> PatternFill:
        if f not in self._fills:
            self._fills[f] = (PatternFill("solid", fgColor=f.color) if f.back is None
                              else PatternFill("solid", start_color=f.color, end_color=f.back))
        return self._fills[f]

    def align(self, a: Align) -> Alignment:
        if a not in self._aligns:
            self._aligns[a] = Alignment(horizontal=a.horizontal, vertical=a.vertical, wrap_text=a.wrap)
        return self._aligns[a]

    def lock(self, locked: bool) -> Protection:
        return self._locks[locked]


def _put(ws, row: int, col: int, item: Any, styles: _Styles, *, header: bool) -> None:
    cell = item if isinstance(item, Cell) else Cell(item, bold=header)
    plain = not (cell.bold or cell.fill or cell.align or cell.locked is not None)
    if cell.value is None and plain:
        return
    c = ws.cell(row=row, column=col, value=clean(cell.value, guard=not cell.raw))
    if cell.bold:
        c.font = _BOLD
    if cell.fill:
        c.fill = styles.fill(cell.fill)
    if cell.align:
        c.alignment = styles.align(cell.align)
    if cell.locked is not None:
        c.protection = styles.lock(cell.locked)


def write(sheets: Iterable[Sheet]) -> bytes:
    wb = Workbook()
    styles = _Styles()
    first = True
    for sheet in sheets:
        ws = wb.active if first else wb.create_sheet()
        first = False
        ws.title = sheet.title
        row = 1
        if sheet.header is not None:
            for col, item in enumerate(sheet.header, start=1):
                _put(ws, row, col, item, styles, header=True)
            row += 1
        for values in sheet.rows:
            for col, item in enumerate(values, start=1):
                _put(ws, row, col, item, styles, header=False)
            row += 1
        for index, column in sheet.columns.items():
            dim = ws.column_dimensions[get_column_letter(index)]
            if column.width is not None:
                dim.width = column.width
            if column.locked is not None:
                dim.protection = styles.lock(column.locked)
        if sheet.freeze:
            ws.freeze_panes = sheet.freeze
        if sheet.protect is not None:
            ws.protection.sheet = True
            ws.protection.formatColumns = not sheet.protect.allow_format_columns
            ws.protection.formatCells = not sheet.protect.allow_format_cells
        if sheet.hidden:
            ws.sheet_state = "hidden"
        for v in sheet.validations:
            dv = DataValidation(type="list", formula1=f"{quote_sheetname(v.source_sheet)}!{v.source_cells}",
                                allow_blank=True, showErrorMessage=False)
            dv.add(v.cells)
            ws.add_data_validation(dv)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class Reader:
    """Значения листов файла XLSX (формулы — вычисленными значениями)."""

    def __init__(self, wb) -> None:
        self._wb = wb
        self.sheets: list[str] = list(wb.sheetnames)

    def rows(self, sheet: str, *, max_col: int | None = None, max_row: int | None = None) -> Iterator[tuple]:
        return self._wb[sheet].iter_rows(min_row=1, max_row=max_row, max_col=max_col, values_only=True)

    def close(self) -> None:
        self._wb.close()

    def __enter__(self) -> Reader:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def open_reader(data: bytes, *, max_bytes: int, max_unpacked_bytes: int) -> Reader:
    """Открыть файл для чтения. XlsxError — файл слишком велик (в том числе после распаковки:
    защита от zip-бомбы), не XLSX или не читается."""
    if len(data) > max_bytes:
        raise XlsxError("too_large")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if sum(i.file_size for i in z.infolist()) > max_unpacked_bytes:
                raise XlsxError("unpacked_too_large")
    except (zipfile.BadZipFile, OSError):
        raise XlsxError("not_xlsx") from None
    try:
        return Reader(load_workbook(io.BytesIO(data), read_only=True, data_only=True))
    except Exception:  # noqa: BLE001 — любой мусор вместо xlsx это ошибка файла, а не сбой
        raise XlsxError("unreadable") from None
