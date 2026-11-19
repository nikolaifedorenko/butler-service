"""Порты exchange: преобразователь DOCX в PDF. Реализация — адаптер Gotenberg; подмена в тестах —
любой объект с теми же методами."""
from __future__ import annotations

from typing import Protocol


class PdfUnavailable(Exception):
    """Сервис PDF не смог собрать документ; текст понятен пользователю и попадает в ответ API."""


class PdfConverter(Protocol):
    def convert(self, docx: bytes, filename: str) -> bytes:
        """PDF из DOCX. Бросает PdfUnavailable."""

    def check(self) -> None:
        """Сервис отвечает. Бросает PdfUnavailable."""
