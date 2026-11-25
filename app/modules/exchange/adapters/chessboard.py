"""Печатная шахматка и список броней в одной книге."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.page import PageMargins
from PIL import ImageFont

from .xlsx import clean

NAVY = "1C3855"
INK = "203D58"
PALE = "DDE8F2"
GRID = "D8E1E9"
FONT = "DejaVu Sans"
HALF_WIDTH = 2.65
FONT_FILE = Path(__file__).resolve().parents[4] / "assets/fonts/DejaVuSans-Bold.ttf"

type Value = str | int
type Fields = list[tuple[str, Value]]


@dataclass
class Band:
    start: int
    end: int
    text: str
    color: str
    fields: Fields


@dataclass
class Room:
    label: str
    category: str
    bands: list[Band] = field(default_factory=list)
    off: list[tuple[int, int]] = field(default_factory=list)
    changes: str = ""


@dataclass
class Chessboard:
    days: list[date]
    rooms: list[Room]
    legend: dict[str, str]
    headings: list[str]
    bookings: list[list[Value]]
    criteria: str = ""


def _fill(color):
    return PatternFill("solid", fgColor=color)


def _layout(sheet, column, last_row, repeat):
    sheet.sheet_view.showGridLines = False
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.page_margins = PageMargins(left=.32, right=.32, top=.29, bottom=.30, header=.14, footer=.14)
    sheet.print_options.horizontalCentered = True
    sheet.oddFooter.right.text = "Страница &P"
    sheet.print_options.gridLines = False
    sheet.print_area = f"A1:{get_column_letter(column)}{last_row}"
    sheet.print_title_rows = repeat


def _cell(sheet, row, col, value="", *, bg="FFFFFF", color=INK, bold=False, size=10, align="left", wrap=False,
          left=None, bottom=None):
    cell = sheet.cell(row, col, clean(value, guard=False))
    # Строка из справочника, фамилия или примечание остаются текстом, в том числе с начальным "=".
    if isinstance(value, str):
        cell.data_type = "s"
    cell.fill = _fill(bg)
    cell.font = Font(name=FONT, color=color, bold=bold, size=size)
    cell.alignment = Alignment(horizontal=align, vertical="center", wrap_text=wrap)
    if left or bottom:
        cell.border = Border(left=Side(style="thin", color=left) if left else Side(),
                             bottom=Side(style="thin", color=bottom) if bottom else Side())
    return cell


def _title(sheet, text, last_col):
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    _cell(sheet, 1, 1, text, bg=NAVY, color="FFFFFF", bold=True, size=14)
    sheet.row_dimensions[1].height = 24


def _band_lanes(bands: list[Band], first: int, last: int) -> list[list[tuple[Band, int, int]]]:
    """Конфликтующие полосы остаются внутри строки объекта на отдельных дорожках."""
    lanes: list[list[tuple[Band, int, int]]] = [[]]
    for band in sorted(bands, key=lambda b: (b.start, b.end, b.text)):
        lo, hi = max(first, band.start), min(last, band.end)
        if lo > hi:
            continue
        lane = next((items for items in lanes if not items or items[-1][2] < lo), None)
        if lane is None:
            lane = []
            lanes.append(lane)
        lane.append((band, lo, hi))
    return lanes


def _room_rows(sheet, room, row, days, notes, font):
    start = 2 * days[0].toordinal()
    end = start + 2 * len(days) - 1
    lanes = _band_lanes(room.bands, start, end)
    if len(lanes) > 1:
        sheet.merge_cells(start_row=row, start_column=1, end_row=row + len(lanes) - 1, end_column=1)
    label = _cell(sheet, row, 1, room.label, bg="F2F6FA", bold=True, align="center", bottom=GRID)
    if room.changes:
        _note(label, room.changes, notes)
    for lane in lanes:
        sheet.row_dimensions[row].height = 13
        for i, day in enumerate(days):
            unavailable = any(a <= day.toordinal() <= b for a, b in room.off)
            bg = "D9E0E7" if unavailable else "FAF3EF" if day.weekday() >= 5 else "FFFFFF"
            for half in (0, 1):
                line = "8196AA" if half == 0 and day.weekday() == 0 else GRID if half == 0 else None
                _cell(sheet, row, 2 + 2 * i + half, bg=bg, bottom=GRID, left=line)
        for band, lo, hi in lane:
            left, right = lo - start + 2, hi - start + 2
            if left < right:
                sheet.merge_cells(start_row=row, start_column=left, end_row=row, end_column=right)
            size = 9 if right - left < 3 else 11
            text_width = font.getlength(band.text) * size / 30
            align = "left" if text_width > (right - left + 1) * 19 - 4 else "center"
            color = _contrast(band.color)
            cell = _cell(sheet, row, left, band.text, bg=band.color, color=color, bold=True, size=size,
                         align=align, left=GRID, bottom=GRID)
            # Заливка всей полосы нужна и в Excel, и в LibreOffice.
            for col in range(left + 1, right + 1):
                sheet.cell(row, col).fill = _fill(band.color)
            fields = (f"{key}:\t{' '.join(str(value).split())}" for key, value in band.fields)
            _note(cell, "\n".join(fields), notes)
        row += 1
    return row


def _contrast(color):
    r, g, b = (int(color[i:i + 2], 16) for i in (0, 2, 4))
    return "FFFFFF" if (299 * r + 587 * g + 114 * b) < 150000 else INK


def _note(cell, text, notes):
    text = clean(text, guard=False)
    note = Comment(text, "Шахматка")
    note.width = 420
    note.height = max(120, 40 + 20 * len(text.splitlines()))
    cell.comment = note
    notes[cell.coordinate] = text


def write(workbook: Chessboard) -> tuple[bytes, dict[str, str]]:
    book = Workbook()
    sheet = book.active
    sheet.title = "Шахматка"
    sheet.freeze_panes = "B5"
    sheet.column_dimensions["A"].width = 17
    days = workbook.days
    last_col = 1 + 2 * len(days)
    for col in range(2, last_col + 1):
        sheet.column_dimensions[get_column_letter(col)].width = HALF_WIDTH

    # Ни одно объединение не пересекает закреплённую колонку A.
    sheet.row_dimensions[1].height = 24
    _cell(sheet, 1, 1, "Шахматка", bg=NAVY, color="FFFFFF", bold=True, size=14)
    for col in range(2, last_col + 1):
        _cell(sheet, 1, col, bg=NAVY)
    months = ("Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
              "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь")
    period = f"{months[days[0].month - 1]} {days[0].year}"
    _cell(sheet, 2, 1, period, bg="F2F6FA", bold=True, size=9)
    sheet.merge_cells(start_row=2, start_column=2, end_row=2, end_column=last_col)
    subtitle = "Левая половина дня — утро, правая — вечер"
    if workbook.criteria:
        subtitle += f" · {workbook.criteria}"
    sheet.row_dimensions[2].height = min(54, 14 + 12 * (len(subtitle) // 160))
    _cell(sheet, 2, 2, subtitle, bg="F2F6FA", size=9, wrap=True)
    sheet.merge_cells("A3:A4")
    _cell(sheet, 3, 1, "Объект", bg=PALE, bold=True, align="center")
    for i, day in enumerate(days):
        col = 2 + 2 * i
        weekday = day.weekday()
        bg = "F7E9E3" if weekday >= 5 else "E9F0F6"
        for row, value in ((3, ("ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС")[weekday]), (4, day.day)):
            sheet.merge_cells(start_row=row, start_column=col, end_row=row, end_column=col + 1)
            _cell(sheet, row, col, value, bg=bg, bold=True, align="center", left=GRID)

    notes: dict[str, str] = {}
    row = 5
    previous = None
    font = ImageFont.truetype(str(FONT_FILE), 40)
    for room in workbook.rooms:
        if room.category != previous:
            sheet.row_dimensions[row].height = 13
            _cell(sheet, row, 1, room.category, bg=PALE, bold=True, size=9)
            for col in range(2, last_col + 1):
                _cell(sheet, row, col, bg=PALE)
            row += 1
            previous = room.category
        row = _room_rows(sheet, room, row, days, notes, font)
    if not workbook.rooms:
        _cell(sheet, row, 2, "Объектов по фильтру нет")
        row += 1
    _layout(sheet, last_col, row - 1, "1:4")

    legend = book.create_sheet("Легенда")
    _title(legend, "Легенда меток", 2)
    legend.column_dimensions["A"].width = 14
    legend.column_dimensions["B"].width = 43
    for col, value in enumerate(("Цвет", "Метка"), start=1):
        _cell(legend, 2, col, value, bg=PALE, bold=True)
    for i, (name, color) in enumerate(workbook.legend.items(), start=3):
        legend.row_dimensions[i].height = 22
        _cell(legend, i, 1, bg=color)
        _cell(legend, i, 2, name, bg="F2F6FA")
    _layout(legend, 2, 2 + len(workbook.legend), "1:2")

    report = book.create_sheet("Список броней")
    _title(report, f"Список броней · {period.lower()}", len(workbook.headings))
    report.freeze_panes = "A3"
    widths = {"Бронь": 15, "Гость": 24, "Объект": 16, "Категория": 13, "Заезд": 22, "Выезд": 22,
              "Гостей": 9, "Метка": 24, "Примечание": 32, "Заказчик": 22, "Статус": 17}
    for col, name in enumerate(workbook.headings, start=1):
        report.column_dimensions[get_column_letter(col)].width = widths.get(name, 16)
        _cell(report, 2, col, name, bg=PALE, bold=True)
    for row, booking in enumerate(workbook.bookings, start=3):
        lines = max((sum(len(line) // max(1, widths.get(name, 16) - 3) + 1 for line in str(value).split("\n"))
                     for name, value in zip(workbook.headings, booking, strict=True)), default=1)
        report.row_dimensions[row].height = min(390, max(17, 13 * lines + 4))
        for col, (name, value) in enumerate(zip(workbook.headings, booking, strict=True), start=1):
            label_fill = workbook.legend.get(str(value)) if name == "Метка" else None
            _cell(report, row, col, value, bg=label_fill or ("F2F6FA" if row % 2 == 0 else "FFFFFF"),
                  color=_contrast(label_fill) if label_fill else INK, wrap=True)
    end_row = 2 + len(workbook.bookings)
    report.auto_filter.ref = f"A2:{get_column_letter(len(workbook.headings))}{end_row}"
    _layout(report, len(workbook.headings), end_row, "1:2")
    stream = BytesIO()
    book.save(stream)
    return stream.getvalue(), notes
