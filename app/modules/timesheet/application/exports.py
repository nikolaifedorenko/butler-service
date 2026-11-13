"""Формы выгрузки Табеля и Графика: описание листов Excel и документа для PDF по данным экрана.

Данные — те же словари, что отдают экраны «График» и «Управленческий Табель»; файл
собирает модуль exchange.
"""
from __future__ import annotations

import re

from app.modules.exchange.application.documents import Document, Page, Paragraph, Run, Table, TCell, text
from app.modules.exchange.application.tables import Align, Cell, Column, Fill, Sheet
from app.modules.people.application import sorted_groups

_CENTER = Align(horizontal="center", vertical="center", wrap=True)
_MIDDLE = Align(vertical="center")
_TOP_WRAP = Align(vertical="top", wrap=True)


_hex_re = re.compile(r"^#?([0-9a-fA-F]{6})$")


def cell_plan_text(cell: dict) -> str:
    """Содержимое ячейки Графика — как на экране: плашка «Выходной за часы» при отсутствии на
    всё рабочее окно, иначе видимые отрезки смены (смена минус отсутствия) по строке на
    отрезок, без смены — значение/код Табеля. Общий источник PDF и Excel."""
    if any(a.get("whole_shift") for a in (cell.get("absences") or [])):
        return "Выходной за часы"
    segments = cell.get("segments") or []
    if segments:
        return "\n".join(f"{s[0]}–{s[1]}" for s in segments)
    shifts = cell.get("shifts") or []
    if shifts:   # payload без segments (кеш) — интервалы самих смен
        return "\n".join(f"{s.get('start_hm', '')}–{s.get('end_hm', '')}" for s in shifts)
    t = cell.get("tabel") or {}
    return t.get("value") or t.get("code") or ""


def tint_hex(color, factor: float = 0.22) -> str | None:
    """Подложка ячейки как на экране: цвет словаря, смешанный с белым.
    Возвращает RRGGBB без «#»; None — цвет не распознан."""
    m = _hex_re.match(str(color or "").strip())
    if not m:
        return None
    h = m.group(1)
    out = []
    for i in (0, 2, 4):
        v = int(h[i:i + 2], 16)
        out.append(round(255 - (255 - v) * factor))
    return f"{out[0]:02X}{out[1]:02X}{out[2]:02X}"


def schedule_sheet(data: dict, year: int, month: int) -> Sheet:
    """График: тот же вид ячейки, что на экране, — время смены (отрезки по строкам), плашка
    «Выходной за часы», цвет из словаря «Смены и отсутствия»; итоговой колонки «Часов» нет."""
    days = [d["date"] for d in data["days"]]
    rows = []
    for row in data["rows"]:
        cells = []
        for iso in days:
            cell = row["cells"].get(iso) or {}
            tint = tint_hex(cell.get("color"))
            cells.append(Cell(cell_plan_text(cell), align=_CENTER, fill=Fill(tint, tint) if tint else None))
        rows.append([Cell(row["employee"]["full_name"], align=_MIDDLE), *cells])
    columns = {1: Column(32), **{i: Column(13.5) for i in range(2, len(days) + 2)}}
    return Sheet(f"График {month:02d}.{year}", header=["Сотрудник", *[d[8:] for d in days]],
                 rows=rows, columns=columns)


def mgmt_sheet(data: dict, year: int, month: int) -> Sheet:
    """УТ: «ФИО × дни», ячейка «ДЯ2 3 ДН 1», итоги по кодам и банк."""
    days = data["days"]
    tariffs = data["tariffs"]
    header = ["ФИО", "Табельный №", *[d[8:] for d in days], *tariffs,
              "Недостача", "Банк на закрытие", "Статус"]
    rows = []
    for r in data["rows"]:
        if r.get("error"):
            values = [r["employee"]["full_name"], r["employee"]["tab_number"], r["error"]]
        else:
            values = [r["employee"]["full_name"], r["employee"]["tab_number"],
                      *[" ".join(f"{t} {h / 60:g}" for t, h in r["ut"].get(d, {}).items()) for d in days],
                      *[r["totals"].get(t, 0) / 60 for t in tariffs],
                      r["debt"]["residual_h"], r["bank"]["closed_h"],
                      "закрыт" if r["state"]["closed"] else "просмотр"]
        values += [None] * (len(header) - len(values))
        rows.append([Cell(v, align=_TOP_WRAP) for v in values])
    return Sheet(f"УТ {month:02d}.{year}", header=header, rows=rows, columns={1: Column(34)})


# ── График для PDF: альбомная A4, узкие поля — влезает весь месяц ──
_PAGE = Page(width_mm=297.0, height_mm=210.0, margin_x_mm=6.0, margin_y_mm=9.0, landscape=True)
_USABLE_MM = _PAGE.width_mm - 2 * _PAGE.margin_x_mm
_NAME_MM = 29.0
_MUTED = "5D6C85"
_HEAD_FILL = "E8EEF7"       # шапка
_WEEKEND_FILL = "F1F4FA"    # выходные в шапке
_GROUP_FILL = "EEF2F8"      # строка блока
_INACTIVE_FILL = "ECEFF4"   # дни вне периодов работы
_OUT_FILL = "D8D3E8"        # «чужие» дни при переходе между сменами


def _grid_cell(value: str, size: float, *, bold: bool = False, align: str = "center", color: str | None = None,
               fill: str | None = None) -> TCell:
    return TCell((text(value, size=size, bold=bold, color=color, align=align, space_before=0, space_after=0),),
                 fill=fill, valign="center")


def _name_cell(name: str, sub: str) -> TCell:
    """ФИО + должность второй строкой (левый край, как в экранной сетке)."""
    blocks = [text(name or "", size=7.5, bold=True, align="left", space_before=0, space_after=0)]
    if sub:
        blocks.append(Paragraph((Run(sub, size=6.0, color=_MUTED),), "left", 0, 0))
    return TCell(tuple(blocks), valign="center")


def _day_cell(cell: dict, day: dict, out: bool) -> TCell:
    weekend = _WEEKEND_FILL if day.get("is_weekend") else None
    tabel = cell.get("tabel") or {}
    shifts = cell.get("shifts") or []
    if not cell.get("employed", True):
        return _grid_cell("—", 6, color=_MUTED, fill=_INACTIVE_FILL)
    if out:
        return _grid_cell("—", 6, color=_MUTED, fill=_OUT_FILL)
    if not (tabel or shifts):
        return _grid_cell("", 6, fill=weekend)
    # тот же вид, что на экране и в «Печати»: плашка «Выходной за часы» на весь день, иначе
    # отрезки смены по строкам (без кода Табеля), без смены — код Табеля; цвет — из словаря
    absences = cell.get("absences") or []
    badge = any(a.get("whole_shift") for a in absences)
    value = cell_plan_text(cell).replace("\u2013", "-")
    if badge:
        value = value.replace("Выходной за часы", "Выходной\nза часы")
        size = 5.2
    elif shifts:
        size = 5.2
        if absences:
            value += "\n*"   # логический разрез (v7/R17)
    else:
        size = 5.6
        if absences:
            value += "*"
    bold = bool(tabel.get("code") == "Я") and bool(shifts) and not badge
    return _grid_cell(value, size, bold=bold, fill=tint_hex(cell.get("color")) or weekend)


def schedule_document(data: dict) -> Document:
    """Тот же вид, что и «Печать»/Excel: блоки смен, строки сотрудников, код смены в ячейке
    (звёздочка — согласованное отсутствие части смены). Итоговой колонки «Часов» нет."""
    year = data["year"]
    days = data["days"]
    ndays = max(1, len(days))
    month_name = data.get("month_name", "")

    header = [_grid_cell("Сотрудник", 7.5, bold=True, align="left", fill=_HEAD_FILL)]
    for d in days:
        header.append(_grid_cell(f"{d['day']:02d}\n{d['weekday']}" + ("\n×2" if d.get("double_scope") else ""),
                                 5.8, bold=True, fill=_WEEKEND_FILL if d.get("is_weekend") else _HEAD_FILL))
    header += [TCell()] * (ndays - len(days))
    rows = [header]

    groups: dict[str, list[dict]] = {}
    for row in data["rows"]:
        for b in row.get("blocks") or []:
            groups.setdefault(b["group"] or "Без группы", []).append(row)
    for gname in sorted_groups(groups.keys()):
        rows.append([_grid_cell(gname.upper(), 8, bold=True, align="left", fill=_GROUP_FILL),
                     *[TCell(fill=_GROUP_FILL)] * ndays])
        seen: set[int] = set()
        for row in groups[gname]:
            if row["employee"]["id"] in seen and gname not in [b["group"] for b in row["blocks"]]:
                continue
            seen.add(row["employee"]["id"])
            block = next((b for b in row["blocks"] if b["group"] == gname), None)
            ranges = (block or {}).get("ranges") or []
            emp = row["employee"]
            line = [_name_cell(emp["full_name"], emp.get("position") or "")]
            for d in days:
                iso = d["date"]
                out = bool(ranges) and not any(
                    rg["start"] <= iso and (not rg["end"] or iso <= rg["end"]) for rg in ranges)
                line.append(_day_cell(row["cells"].get(iso) or {}, d, out))
            rows.append(line)

    blocks: list = [
        text(f"График сменности, {month_name} {year} г.", size=13, bold=True, space_after=2),
        text("План по блокам: отрезки смен по строкам, цвет — из словаря «Смены и "
             "отсутствия». Плашка «Выходной за часы» — отсутствие на всю смену; "
             "* — согласованное отсутствие; «—» — вне периода работы; ×2 в шапке — "
             "день двойной оплаты. Внутри блока: старшие, далее по алфавиту.",
             size=8, color=_MUTED, space_after=5),
        Table(rows, (_NAME_MM, *[(_USABLE_MM - _NAME_MM) / ndays] * ndays), header_rows=1, fixed=True),
    ]
    # расшифровка значений Табеля, встречающихся в месяце
    seen_values: dict[str, None] = {}
    for row in data["rows"]:
        for cell in row["cells"].values():
            t = cell.get("tabel") or {}
            value = t.get("value") or t.get("code")
            if value:
                seen_values.setdefault(value, None)
    if seen_values:
        blocks.append(text("Значения Табеля: " + " · ".join(sorted(seen_values))
                           + "  ·  * — согласованное отсутствие (логический разрез смены)",
                           size=7, color=_MUTED, space_before=6))
    footer = text(f"График сменности · {month_name} {year} · «Батлер Сервис»", size=7.5, color=_MUTED, align="center")
    return Document(blocks, page=_PAGE, footer=footer)
