"""Документы: DOCX по описанию, шаблоны с плейсхолдерами {field}, PDF из DOCX.

Пример:
    write_docx(Document([text("НОЧНОЙ ОТЧЁТ", bold=True, size=14, align="center")]))
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from app.core.config import settings
from app.core.media import BASE_DIR

from ..adapters import docx
from ..adapters.gotenberg import GotenbergConverter
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
from ..ports import PdfConverter, PdfUnavailable

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
_HEALTH_TTL_SECONDS = 15.0
_converter: PdfConverter | None = None
_converter_ready = False
_health: tuple[float, str] | None = None       # (когда проверено, "" — сервис отвечает, иначе причина)


def set_pdf_converter(converter: PdfConverter | None) -> None:
    """Подменить преобразователь (тесты, composition root); None — вернуть настройку по умолчанию."""
    global _converter, _converter_ready, _health
    _converter, _converter_ready, _health = converter, converter is not None, None


def _pdf_converter() -> PdfConverter | None:
    global _converter, _converter_ready
    if not _converter_ready:
        url = (settings.gotenberg_url or "").strip()
        _converter = GotenbergConverter(url, settings.gotenberg_timeout_seconds) if url else None
        _converter_ready = True
    return _converter


def _unconfigured() -> str:
    return "сервис PDF не настроен (задайте GOTENBERG_URL)."


def docx_to_pdf(docx_bytes: bytes, filename: str = "document.pdf") -> tuple[bytes | None, str]:
    """PDF из DOCX. Возвращает (байты или None, чем сделано либо почему не вышло)."""
    converter = _pdf_converter()
    if converter is None:
        return None, _unconfigured()
    try:
        return converter.convert(docx_bytes, filename), "gotenberg"
    except PdfUnavailable as exc:
        return None, str(exc)


def pdf_error() -> str:
    """Почему PDF недоступен ("" — доступен). Ответ сервиса запоминается на несколько секунд."""
    global _health
    converter = _pdf_converter()
    if converter is None:
        return _unconfigured()
    moment = time.monotonic()
    if _health is None or moment - _health[0] > _HEALTH_TTL_SECONDS:
        try:
            converter.check()
            _health = (moment, "")
        except PdfUnavailable as exc:
            _health = (moment, str(exc))
    return _health[1]


def pdf_mode() -> str:
    """gotenberg | none — может ли сервер делать PDF."""
    return "none" if pdf_error() else "gotenberg"


def pdf_unavailable_detail(how: str) -> str:
    """Текст для пользователя, когда PDF собрать не удалось: чем заменить и что проверить."""
    return (f"PDF на сервере собрать не удалось: {how} "
            "Проверьте контейнер gotenberg и адрес GOTENBERG_URL. "
            "Без PDF работают «Печать» в браузере, DOCX и выгрузка Excel.")
