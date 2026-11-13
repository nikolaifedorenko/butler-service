"""Модуль exchange: запись XLSX и CSV по описанию, чтение XLSX."""
from __future__ import annotations

import datetime as dt
import io
import zipfile

import pytest
from openpyxl import load_workbook

from app.modules.exchange.application.tables import (
    Align,
    Cell,
    Column,
    Fill,
    ListValidation,
    Protect,
    Sheet,
    XlsxError,
    open_xlsx,
    raw,
    write_csv,
    write_xlsx,
)

LIMITS = {"max_bytes": 1_000_000, "max_unpacked_bytes": 10_000_000}


def _book(*sheets: Sheet):
    return load_workbook(io.BytesIO(write_xlsx(sheets)))


def test_header_is_bold_and_rows_follow():
    ws = _book(Sheet("Лист", header=["A", "B"], rows=[[1, "x"], [2, "y"]])).active
    assert ws.title == "Лист"
    assert [c.value for c in ws[1]] == ["A", "B"] and all(c.font.b for c in ws[1])
    assert [[c.value for c in r] for r in ws.iter_rows(min_row=2)] == [[1, "x"], [2, "y"]]
    assert not ws["A2"].font.b


def test_sheet_without_header_starts_at_first_row():
    ws = _book(Sheet("Лист", rows=[["x"]])).active
    assert ws["A1"].value == "x" and not ws["A1"].font.b


def test_empty_row_leaves_gap_and_none_creates_no_cell():
    ws = _book(Sheet("Лист", header=["A"], rows=[["x", None, "z"], [], ["last"]])).active
    assert ws["A4"].value == "last" and ws["A3"].value is None
    assert ws["B2"].value is None and ws["C2"].value == "z"


@pytest.mark.parametrize("text", ["=1+1", "+7", "-5", "@SUM(A1)", "\tx", "\rx"])
def test_text_that_looks_like_formula_is_guarded(text):
    ws = _book(Sheet("Лист", rows=[[text, Cell(text, bold=True)]])).active
    assert ws["A1"].value == "'" + text and ws["B1"].value == "'" + text
    assert ws["A1"].data_type == "s"


def test_raw_cell_skips_formula_guard_but_numbers_stay_numbers():
    ws = _book(Sheet("Лист", rows=[[raw("-100123"), -5, 1.5, dt.date(2026, 11, 12)]])).active
    assert ws["A1"].value == "-100123"
    assert ws["B1"].value == -5 and ws["C1"].value == 1.5
    assert ws["D1"].value == dt.datetime(2026, 11, 12)


def test_control_characters_are_removed_instead_of_failing():
    ws = _book(Sheet("Лист", rows=[["до\x00\x0bпосле", raw("a\x01b")]])).active
    assert ws["A1"].value == "допосле" and ws["B1"].value == "ab"


def test_cell_formatting():
    cell = Cell("x", bold=True, fill=Fill("DCE6F5"), align=Align("center", "top", wrap=True), locked=False)
    ws = _book(Sheet("Лист", rows=[[cell, Cell(None, fill=Fill("AABBCC", "AABBCC"))]])).active
    a = ws["A1"]
    assert a.font.b and a.fill.fill_type == "solid" and a.fill.fgColor.rgb == "00DCE6F5"
    assert (a.alignment.horizontal, a.alignment.vertical, a.alignment.wrap_text) == ("center", "top", True)
    assert a.protection.locked is False
    b = ws["B1"]
    assert b.value is None and b.fill.fgColor.rgb == "00AABBCC" and b.fill.bgColor.rgb == "00AABBCC"


def test_columns_freeze_protection_hidden():
    wb = _book(
        Sheet("Данные", header=["ID", "имя"], rows=[[1, "a"]], columns={1: Column(16, locked=True), 2: Column(28)},
              freeze="A2", protect=Protect(allow_format_columns=True, allow_format_cells=True)),
        Sheet("Списки", rows=[["x"]], protect=Protect(), hidden=True))
    ws = wb["Данные"]
    assert ws.column_dimensions["A"].width == 16 and ws.column_dimensions["B"].width == 28
    assert ws.freeze_panes == "A2"
    assert ws.protection.sheet and not ws.protection.formatColumns and not ws.protection.formatCells
    lists = wb["Списки"]
    assert lists.sheet_state == "hidden" and lists.protection.sheet and lists.protection.formatCells
    assert wb.sheetnames == ["Данные", "Списки"]


def test_list_validation_points_to_other_sheet():
    wb = _book(Sheet("Дерево", header=["узел"], validations=[ListValidation("A2:A100", "Мои списки", "$A$2:$A$5")]),
               Sheet("Мои списки", rows=[["a"]]))
    (dv,) = wb["Дерево"].data_validations.dataValidation
    assert dv.type == "list" and dv.formula1 == "'Мои списки'!$A$2:$A$5" and str(dv.sqref) == "A2:A100"
    assert dv.allow_blank and not dv.showErrorMessage


def test_rows_may_be_a_generator():
    ws = _book(Sheet("Лист", header=["n"], rows=([i] for i in range(3)))).active
    assert [r[0].value for r in ws.iter_rows(min_row=2)] == [0, 1, 2]


def test_read_back_values():
    data = write_xlsx([Sheet("Один", header=["a", "b"], rows=[[1, "x"], [2, None]]), Sheet("Два", rows=[["z"]])])
    with open_xlsx(data, **LIMITS) as book:
        assert book.sheets == ["Один", "Два"]
        assert list(book.rows("Один")) == [("a", "b"), (1, "x"), (2, None)]
        assert list(book.rows("Один", max_row=1, max_col=1)) == [("a",)]


def test_reader_rejects_bad_files():
    good = write_xlsx([Sheet("Лист", rows=[["x" * 5000]])])
    with pytest.raises(XlsxError) as e:
        open_xlsx(good, max_bytes=10, max_unpacked_bytes=10_000_000)
    assert e.value.kind == "too_large"
    with pytest.raises(XlsxError) as e:
        open_xlsx(good, max_bytes=1_000_000, max_unpacked_bytes=100)
    assert e.value.kind == "unpacked_too_large"
    with pytest.raises(XlsxError) as e:
        open_xlsx(b"not a zip", **LIMITS)
    assert e.value.kind == "not_xlsx"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("hello.txt", "zip, но не xlsx")
    with pytest.raises(XlsxError) as e:
        open_xlsx(buf.getvalue(), **LIMITS)
    assert e.value.kind == "unreadable"


def test_csv_has_bom_semicolons_and_formula_guard():
    data = write_csv(["Время", "Кто"], [["2026-11-12", "=cmd"], [raw("-100123"), raw("@channel")], [5, "a;b"]])
    text = data.decode("utf-8")
    assert text.startswith("﻿")
    assert text[1:].split("\r\n") == ["Время;Кто", "2026-11-12;'=cmd", "-100123;@channel", '5;"a;b"', ""]
