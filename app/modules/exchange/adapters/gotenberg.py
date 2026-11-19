"""PDF из DOCX через Gotenberg (отдельный контейнер с LibreOffice): документ выглядит как в Word,
включая подложку, колонтитулы и сложную вёрстку бланка. Шрифты с кириллицей контейнер берёт из
каталога assets/fonts проекта (том в compose)."""
from __future__ import annotations

import httpx

from ..ports import PdfUnavailable

_CONVERT_PATH = "/forms/libreoffice/convert"
_HEALTH_PATH = "/health"
_DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class GotenbergConverter:
    def __init__(self, base_url: str, timeout: float = 60.0, transport: httpx.BaseTransport | None = None):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._transport = transport          # подмена сети в тестах

    def _client(self, timeout: float) -> httpx.Client:
        return httpx.Client(base_url=self._base_url, timeout=timeout, transport=self._transport)

    def convert(self, docx: bytes, filename: str) -> bytes:
        try:
            with self._client(self._timeout) as client:
                response = client.post(_CONVERT_PATH, files={"files": ("document.docx", docx, _DOCX_TYPE)})
        except httpx.HTTPError as exc:
            raise PdfUnavailable(f"сервис PDF не отвечает ({type(exc).__name__}).") from exc
        if response.status_code != 200:
            raise PdfUnavailable(f"сервис PDF вернул ошибку {response.status_code}.")
        if not response.content.startswith(b"%PDF"):
            raise PdfUnavailable("сервис PDF вернул не PDF.")
        return response.content

    def check(self) -> None:
        try:
            with self._client(3.0) as client:
                response = client.get(_HEALTH_PATH)
        except httpx.HTTPError as exc:
            raise PdfUnavailable(f"сервис PDF не отвечает ({type(exc).__name__}).") from exc
        if response.status_code != 200:
            raise PdfUnavailable(f"сервис PDF не готов: ответ {response.status_code}.")
