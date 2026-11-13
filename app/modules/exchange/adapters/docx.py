"""DOCX на python-docx: документ по описанию, заполнение шаблонов с плейсхолдерами {field}."""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

from docx import Document as DocxDocument
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor

from ..domain.documents import Document, Paragraph, Picture, Table, TCell

_ALIGN = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER, "right": WD_ALIGN_PARAGRAPH.RIGHT}
PRINT_MAX_PX = 1600   # 6 см в ячейке — это ~700 px при 300 dpi; больше печать не покажет


# ─────────────────────────── документ по описанию ───────────────────────────
def _paragraph(p, spec: Paragraph) -> None:
    if spec.align:
        p.alignment = _ALIGN[spec.align]
    if spec.space_before is not None:
        p.paragraph_format.space_before = Pt(spec.space_before)
    if spec.space_after is not None:
        p.paragraph_format.space_after = Pt(spec.space_after)
    for r in spec.runs:
        run = p.add_run(r.text)
        if r.size is not None:
            run.font.size = Pt(r.size)
        if r.bold is not None:
            run.font.bold = r.bold
        if r.color:
            run.font.color.rgb = RGBColor.from_string(r.color)


def print_copy(path) -> io.BytesIO:
    """Уменьшенная копия фото для документа: оригиналы с телефона (до 12 МБ) делали DOCX и PDF
    на сотни мегабайт в памяти. Поворот по EXIF применяется сразу — иначе Word и PDF показали
    бы снимок с телефона лёжа."""
    from PIL import Image, ImageOps

    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        im.thumbnail((PRINT_MAX_PX, PRINT_MAX_PX))
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "JPEG", quality=85)
    buf.seek(0)
    return buf


def _picture(cell, spec: Picture) -> bool:
    """Вставить картинку в ячейку; False — файла нет или это не картинка (тогда — текст)."""
    target = Path(spec.path) if spec.path else None
    ok = target is not None and target.is_file()
    if ok:
        try:
            source = print_copy(target)
        except Exception:
            source = str(target)      # Pillow не прочитал — оригиналом; не картинку отсеет add_picture
        para = cell.add_paragraph()
        try:
            para.add_run().add_picture(source, width=Mm(spec.width_mm))
        except Exception:
            ok = False
    if not ok and spec.missing_text:
        cell.add_paragraph(spec.missing_text)
    return ok


def _shade(cell, fill: str) -> None:
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), fill)
    cell._tc.get_or_add_tcPr().append(shd)


def _cell(cell, spec: TCell) -> None:
    if spec.valign == "center":
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    first = True
    for block in spec.blocks:
        if isinstance(block, Picture):
            _picture(cell, block)
        else:
            _paragraph(cell.paragraphs[0] if first else cell.add_paragraph(), block)
        first = False
    if spec.fill:
        _shade(cell, spec.fill)


def _fixed_widths(table, widths) -> None:
    """Жёсткая раскладка и узкие поля ячеек (иначе 31 день на лист не влезает)."""
    table.autofit = False
    tbl_pr = table._tbl.tblPr
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tbl_pr.append(layout)
    mar = OxmlElement("w:tblCellMar")
    for side, w in (("top", 15), ("left", 28), ("bottom", 15), ("right", 28)):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:w"), str(w))
        el.set(qn("w:type"), "dxa")
        mar.append(el)
    tbl_pr.append(mar)
    for i, col in enumerate(table.columns):
        if i < len(widths):
            col.width = widths[i]
    _cell_widths(table, widths)


def _cell_widths(table, widths) -> None:
    for row in table.rows:
        for i, cell in enumerate(row.cells):
            if i < len(widths):
                cell.width = widths[i]


def _table(doc, spec: Table) -> None:
    table = doc.add_table(rows=1, cols=len(spec.widths_mm))
    table.style = "Table Grid"
    for n, row in enumerate(spec.rows):
        tr = table.rows[0] if n == 0 else table.add_row()
        if n < spec.header_rows:      # строка повторяется на каждой странице
            el = OxmlElement("w:tblHeader")
            el.set(qn("w:val"), "true")
            tr._tr.get_or_add_trPr().append(el)
        for cell, cell_spec in zip(tr.cells, row, strict=False):
            _cell(cell, cell_spec)
    widths = [Mm(w) for w in spec.widths_mm]
    if spec.fixed:
        _fixed_widths(table, widths)
    else:                             # иначе Word растягивает таблицу как попало
        table.autofit = False
        _cell_widths(table, widths)


def write(spec: Document) -> bytes:
    doc = DocxDocument()
    if spec.font:
        style = doc.styles["Normal"]
        style.font.name = spec.font.name
        style.font.size = Pt(spec.font.size)
    sec = doc.sections[0]
    if spec.page:
        if spec.page.landscape:
            sec.orientation = WD_ORIENT.LANDSCAPE
        sec.page_width, sec.page_height = Mm(spec.page.width_mm), Mm(spec.page.height_mm)
        sec.left_margin = sec.right_margin = Mm(spec.page.margin_x_mm)
        sec.top_margin = sec.bottom_margin = Mm(spec.page.margin_y_mm)
    if spec.footer:
        _paragraph(sec.footer.paragraphs[0], spec.footer)
    for block in spec.blocks:
        if isinstance(block, Table):
            _table(doc, block)
        else:
            _paragraph(doc.add_paragraph(), block)
    return _save(doc)


def _save(doc) -> bytes:
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ─────────────────────────── шаблоны с плейсхолдерами ───────────────────────────
PH_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_MAX_UNCOMPRESSED = 50 * 1024 * 1024   # распакованный docx не больше 50 МБ
_MAX_ZIP_ENTRIES = 2000


def check_template(data: bytes) -> None:
    """ValueError, если файл — не DOCX или слишком велик при распаковке (zip-бомба: лимит на
    загрузку относится к сжатому файлу, а распаковка может раздуть память в разы)."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            infos = zf.infolist()
            if len(infos) > _MAX_ZIP_ENTRIES:
                raise ValueError(f"Слишком много файлов в шаблоне (>{_MAX_ZIP_ENTRIES})")
            if sum(i.file_size for i in infos) > _MAX_UNCOMPRESSED:
                raise ValueError("Шаблон слишком велик при распаковке (> 50 МБ)")
    except zipfile.BadZipFile:
        raise ValueError("Файл не является корректным .docx") from None
    try:
        DocxDocument(io.BytesIO(data))
    except Exception as exc:
        raise ValueError(f"Файл не является корректным .docx: {exc}") from None


def _paragraphs(doc):
    yield from doc.paragraphs
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                yield from cell.paragraphs
    for section in doc.sections:
        for hf in (section.header, section.footer):
            yield from hf.paragraphs


def placeholders(path: Path) -> set[str]:
    found: set[str] = set()
    for p in _paragraphs(DocxDocument(str(path))):
        found.update(PH_RE.findall("".join(r.text for r in p.runs) or p.text))
    return found


def _set_run_text_multiline(run, value: str) -> None:
    lines = value.split("\n")
    run.text = lines[0]
    for extra in lines[1:]:
        run._r.append(run._r.makeelement(qn("w:br"), {}))
        t = run._r.makeelement(qn("w:t"), {})
        t.set(qn("xml:space"), "preserve")
        t.text = extra
        run._r.append(t)


def _fill_paragraph(p, values: dict) -> None:
    """Подставить значения, сохранив оформление: текст пишется в первый фрагмент абзаца.
    Плейсхолдер, разбитый редактором на несколько фрагментов («{full_» + «name}»), склеивается."""
    def sub(source: str) -> str:
        return PH_RE.sub(lambda m: str(values.get(m.group(1), m.group(0))), source)

    runs = p.runs
    if not runs:
        if PH_RE.search(p.text or ""):
            p.text = sub(p.text)
        return
    full = "".join(r.text for r in runs)
    if not PH_RE.search(full):
        return
    new = sub(full)
    if new == full:
        return
    _set_run_text_multiline(runs[0], new)
    for r in runs[1:]:
        r.text = ""


def fill(template: Path | None, values: dict, fallback_text: str) -> bytes:
    """Документ по шаблону; шаблона нет — по тексту fallback_text (строка — абзац)."""
    if template is not None:
        doc = DocxDocument(str(template))
    else:
        doc = DocxDocument()
        for line in fallback_text.split("\n"):
            doc.add_paragraph(line)
    for p in _paragraphs(doc):
        _fill_paragraph(p, values)
    return _save(doc)
