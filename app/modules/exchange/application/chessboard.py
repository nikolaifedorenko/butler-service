"""Публичный формат книги шахматки и её печатный PDF."""
from __future__ import annotations

from app.core.config import settings

from ..adapters.chessboard import Band as Band
from ..adapters.chessboard import Chessboard as Chessboard
from ..adapters.chessboard import Fields as Fields
from ..adapters.chessboard import Room as Room
from ..adapters.chessboard import Value as Value
from ..adapters.chessboard import write as write
from ..adapters.gotenberg import GotenbergConverter
from ..adapters.pdf_notes import compact_notes
from ..ports import PdfUnavailable as PdfUnavailable


def to_pdf(content: bytes, notes: dict[str, str]) -> bytes:
    url = (settings.gotenberg_url or "").strip()
    if not url:
        raise PdfUnavailable("сервис PDF не настроен (задайте GOTENBERG_URL).")
    return compact_notes(GotenbergConverter(url, settings.gotenberg_timeout_seconds).convert_workbook(content), notes)
