"""Документы: DOCX по описанию, шаблоны с плейсхолдерами {field}, PDF из DOCX.

Пример:
    write_docx(Document([text("НОЧНОЙ ОТЧЁТ", bold=True, size=14, align="center")]))
"""
from __future__ import annotations

import re
from pathlib import Path

from app.core.media import BASE_DIR

from ..adapters import docx, pdf_reportlab
from ..domain.documents import (  # noqa: F401 — публичные типы описания документа
    Document,
    Font,
    Page,
    Paragraph,
    Picture,
    Run,
    Table,
    TCell,
    text,
)

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_MEDIA_TYPE = "application/pdf"

# templates/ в корне проекта — том в compose: бланки переживают пересборку образа
TEMPLATES_DIR = BASE_DIR / "templates"
TEMPLATES_DIR.mkdir(exist_ok=True)
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")


def write_docx(document: Document) -> bytes:
    return docx.write(document)


# ─────────────────────────── шаблоны ───────────────────────────
def _template_file(name: str) -> Path:
    if not _NAME_RE.match(name or ""):      # имя файла строится из имени шаблона
        raise ValueError(f"Некорректное имя шаблона: {name!r}")
    return TEMPLATES_DIR / f"{name}.docx"


def template_path(name: str) -> Path | None:
    """Файл загруженного шаблона или None."""
    p = TEMPLATES_DIR / f"{name}.docx"
    return p if p.exists() else None


def save_template(name: str, data: bytes) -> Path:
    """Сохранить шаблон. ValueError — имя недопустимо или файл не DOCX."""
    path = _template_file(name)
    docx.check_template(data)
    path.write_bytes(data)
    return path


def delete_template(name: str) -> bool:
    p = template_path(name)
    if p:
        p.unlink()
        return True
    return False


def template_placeholders(path: Path) -> set[str]:
    """Имена плейсхолдеров {field}, встречающихся в шаблоне."""
    return docx.placeholders(path)


def fill_template(name: str, values: dict, fallback_text: str) -> bytes:
    """DOCX по шаблону name с подставленными значениями: шрифты, стили, колонтитулы и подложка
    шаблона сохраняются. Шаблон не загружен — документ из fallback_text (строка — абзац)."""
    return docx.fill(template_path(name), values, fallback_text)


# ─────────────────────────── PDF ───────────────────────────
def docx_to_pdf(docx_bytes: bytes, filename: str = "document.pdf") -> tuple[bytes | None, str]:
    """PDF из DOCX. Возвращает (байты или None, чем сделано либо почему не вышло)."""
    return pdf_reportlab.docx_to_pdf(docx_bytes, filename)


def pdf_mode() -> str:
    """native | none — может ли сервер делать PDF."""
    return pdf_reportlab.pdf_mode()


def pdf_error() -> str:
    return pdf_reportlab.native_error()


def pdf_unavailable_detail(how: str) -> str:
    """Текст для пользователя, когда PDF собрать не удалось: чем заменить и что проверить."""
    return (f"PDF на сервере собрать не удалось: {how} "
            "Проверьте установку зависимостей: uv sync. "
            "Без PDF работают «Печать» в браузере и выгрузка Excel.")
