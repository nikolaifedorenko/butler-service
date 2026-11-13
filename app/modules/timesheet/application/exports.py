"""Формы выгрузки Табеля и Графика в Excel: описание листов по данным экрана.

Данные — те же словари, что отдают экраны «График» и «Управленческий Табель»; файл
собирает модуль exchange.
"""
from __future__ import annotations

from app.modules.exchange.application.tables import Align, Cell, Column, Fill, Sheet

_CENTER = Align(horizontal="center", vertical="center", wrap=True)
_MIDDLE = Align(vertical="center")
_TOP_WRAP = Align(vertical="top", wrap=True)


def schedule_sheet(data: dict, year: int, month: int) -> Sheet:
    """График: тот же вид ячейки, что на экране, — время смены (отрезки по строкам), плашка
    «Выходной за часы», цвет из словаря «Смены и отсутствия»; итоговой колонки «Часов» нет."""
    from app.modules.docs.application.grid_docx import cell_plan_text, tint_hex

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
