"""Модуль exchange: DOCX по описанию, шаблоны с плейсхолдерами, PDF."""
from __future__ import annotations

import io

import pytest
from docx import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Mm, Pt
from PIL import Image

from app.modules.exchange.application import documents
from app.modules.exchange.application.documents import (
    Document,
    Font,
    Page,
    Paragraph,
    Picture,
    Run,
    Table,
    TCell,
    text,
    write_docx,
)


def _near(value, mm: float) -> bool:
    """Размер совпадает с точностью до единицы хранения DOCX (1/20 пункта = 635 EMU)."""
    return abs(value - Mm(mm)) <= 635


def _open(doc: Document):
    return DocxDocument(io.BytesIO(write_docx(doc)))


def test_text_helper():
    assert text("") == Paragraph()
    assert text("", size=6, bold=False).runs == (Run("", False, 6),)
    assert text("a", align="right") == Paragraph((Run("a"),), "right")


def test_paragraphs_runs_and_formatting():
    d = _open(Document([
        text("Заголовок", bold=True, size=14, align="center", space_after=2),
        Paragraph((Run("Итог: ", bold=True), Run("всё в порядке", color="5D6C85"))),
        text(""),
        text("две\nстроки"),
    ], font=Font("Times New Roman", 10.5)))
    title, mixed, empty, multi = d.paragraphs
    assert title.text == "Заголовок" and title.alignment == WD_ALIGN_PARAGRAPH.CENTER
    assert title.runs[0].bold and title.runs[0].font.size == Pt(14)
    assert title.paragraph_format.space_after == Pt(2)
    assert [r.text for r in mixed.runs] == ["Итог: ", "всё в порядке"]
    assert mixed.runs[0].bold and mixed.runs[1].bold is None
    assert str(mixed.runs[1].font.color.rgb) == "5D6C85"
    assert empty.runs == [] and multi.text == "две\nстроки"
    assert d.styles["Normal"].font.name == "Times New Roman" and d.styles["Normal"].font.size == Pt(10.5)


def test_page_and_footer():
    d = _open(Document([text("x")], page=Page(297, 210, 6, 9, landscape=True),
                       footer=text("подвал", size=7.5, align="center")))
    sec = d.sections[0]
    assert _near(sec.page_width, 297) and _near(sec.page_height, 210)
    assert _near(sec.left_margin, 6) and _near(sec.right_margin, 6) and _near(sec.top_margin, 9)
    assert sec.footer.paragraphs[0].text == "подвал"


def test_table_cells_fill_header_and_widths():
    table = Table([[TCell((text("Пункт", bold=True),), fill="E8EEF7", valign="center"), TCell((text("Итог"),))],
                   [TCell((text("Свет"), text("вторая строка"))), TCell()]],
                  widths_mm=(62, 22), header_rows=1, fixed=True)
    d = _open(Document([table]))
    (t,) = d.tables
    assert [[c.text for c in row.cells] for row in t.rows] == [["Пункт", "Итог"], ["Свет\nвторая строка", ""]]
    xml = t._tbl.xml
    assert 'w:fill="E8EEF7"' in xml and "<w:tblHeader" in xml and 'w:type="fixed"' in xml
    assert _near(t.rows[0].cells[0].width, 62) and _near(t.rows[1].cells[1].width, 22)
    assert t.style.name == "Table Grid"


def test_picture_is_inserted_reduced_and_missing_file_becomes_text(tmp_path):
    photo = tmp_path / "photo.jpg"
    Image.new("RGB", (3000, 2000), (10, 120, 200)).save(photo, "JPEG")
    cell = TCell((text("Комментарий"), Picture(str(photo), 60, "[нет фото]"),
                  Picture(str(tmp_path / "нет.jpg"), 60, "[нет фото]"), Picture("", 60, "[пусто]")))
    d = _open(Document([Table([[cell]], widths_mm=(100,))]))
    c = d.tables[0].rows[0].cells[0]
    assert [p.text for p in c.paragraphs] == ["Комментарий", "", "[нет фото]", "[пусто]"]
    (shape,) = d.inline_shapes
    assert _near(shape.width, 60)
    (image,) = [r.target_part.blob for r in d.part.rels.values() if "image" in r.reltype]
    assert max(Image.open(io.BytesIO(image)).size) <= 1600


def _template(tmp_path, monkeypatch) -> bytes:
    monkeypatch.setattr(documents, "TEMPLATES_DIR", tmp_path)
    src = DocxDocument()
    p = src.add_paragraph()
    p.add_run("от {full_").bold = True          # плейсхолдер разбит редактором на два фрагмента
    p.add_run("name}")
    src.add_table(rows=1, cols=1).cell(0, 0).text = "Период: {period}"
    src.sections[0].footer.paragraphs[0].add_run("{today} · {unknown}")
    buf = io.BytesIO()
    src.save(buf)
    return buf.getvalue()


def test_template_roundtrip(tmp_path, monkeypatch):
    data = _template(tmp_path, monkeypatch)
    assert documents.template_path("vacation") is None
    path = documents.save_template("vacation", data)
    assert path == tmp_path / "vacation.docx" and documents.template_path("vacation") == path
    assert documents.template_placeholders(path) == {"full_name", "period", "today", "unknown"}

    out = DocxDocument(io.BytesIO(documents.fill_template(
        "vacation", {"full_name": "Иванов\nИван", "period": "с 01.10 по 05.10", "today": "12.11.2026"}, "не нужен")))
    first = out.paragraphs[0]
    assert first.text == "от Иванов\nИван" and first.runs[0].bold      # оформление первого фрагмента сохранено
    assert out.tables[0].cell(0, 0).text == "Период: с 01.10 по 05.10"
    assert out.sections[0].footer.paragraphs[0].text == "12.11.2026 · {unknown}"   # неизвестное не трогаем

    assert documents.delete_template("vacation") is True
    assert documents.delete_template("vacation") is False


def test_fill_without_template_uses_fallback_text(tmp_path, monkeypatch):
    monkeypatch.setattr(documents, "TEMPLATES_DIR", tmp_path)
    out = DocxDocument(io.BytesIO(documents.fill_template("day_off", {"n": 2}, "Прошу {n} дня.\n\nПодпись")))
    assert [p.text for p in out.paragraphs] == ["Прошу 2 дня.", "", "Подпись"]


@pytest.mark.parametrize("name", ["", "../etc", "Vacation", "a", "x" * 41, "a/b", "a.b"])
def test_template_name_cannot_escape_directory(tmp_path, monkeypatch, name):
    data = _template(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        documents.save_template(name, data)
    assert list(tmp_path.iterdir()) == []


def test_template_must_be_docx(tmp_path, monkeypatch):
    monkeypatch.setattr(documents, "TEMPLATES_DIR", tmp_path)
    with pytest.raises(ValueError, match="корректным .docx"):
        documents.save_template("vacation", b"not a zip")
    assert list(tmp_path.iterdir()) == []


def test_pdf_from_document():
    if documents.pdf_mode() == "none":
        pytest.skip("нет шрифта с кириллицей для встроенного рендера")
    from pypdf import PdfReader

    pdf, how = documents.docx_to_pdf(write_docx(Document([text("Ночной отчёт"), Table(
        [[TCell((text("Пункт"),)), TCell((text("ОК"),))]], widths_mm=(60, 20))])))
    assert pdf and how == "native"
    assert "Ночной отчёт" in PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
