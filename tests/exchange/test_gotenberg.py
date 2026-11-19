"""PDF из DOCX через Gotenberg: адаптер (сеть подменена), прикладной слой, эндпоинты и — при
заданном GOTENBERG_URL (в CI это контейнер) — настоящая конвертация."""
from __future__ import annotations

import datetime as dt
import io
import os

import httpx
import pytest

from app.modules.exchange.adapters.gotenberg import GotenbergConverter
from app.modules.exchange.application import documents
from app.modules.exchange.application.documents import Document, Table, TCell, text, write_docx
from app.modules.exchange.ports import PdfUnavailable

PDF = b"%PDF-1.7\n%fake\n"


def _converter(handler) -> GotenbergConverter:
    return GotenbergConverter("http://gotenberg:3000", timeout=5, transport=httpx.MockTransport(handler))


class _Fake:
    """Преобразователь без сети; check_error — что ответит проверка готовности."""

    def __init__(self, check_error: str = ""):
        self.check_error = check_error
        self.checks = 0
        self.converted: list[str] = []

    def convert(self, docx: bytes, filename: str) -> bytes:
        self.converted.append(filename)
        return PDF

    def check(self) -> None:
        self.checks += 1
        if self.check_error:
            raise PdfUnavailable(self.check_error)


@pytest.fixture(autouse=True)
def _reset_converter():
    yield
    documents.set_pdf_converter(None)


# ── адаптер ───────────────────────────────────────────────────────────────────

def test_convert_posts_docx_as_multipart_and_returns_pdf():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"], seen["type"], seen["body"] = request.url.path, request.headers["content-type"], request.content
        return httpx.Response(200, content=PDF)

    assert _converter(handler).convert(b"PK-docx", "x.pdf") == PDF
    assert seen["path"] == "/forms/libreoffice/convert"
    assert seen["type"].startswith("multipart/form-data")
    assert b'name="files"' in seen["body"] and b"PK-docx" in seen["body"]


@pytest.mark.parametrize("response, expected", [
    (httpx.Response(500), "ошибку 500"),
    (httpx.Response(200, content=b"<html>"), "не PDF"),
])
def test_convert_refusals_are_pdf_unavailable(response, expected):
    with pytest.raises(PdfUnavailable, match=expected):
        _converter(lambda request: response).convert(b"PK", "x.pdf")


def test_convert_network_failure_is_pdf_unavailable():
    def handler(request):
        raise httpx.ConnectError("нет соединения")

    with pytest.raises(PdfUnavailable, match="не отвечает"):
        _converter(handler).convert(b"PK", "x.pdf")


def test_check_requires_health_200():
    _converter(lambda request: httpx.Response(200, json={"status": "up"})).check()
    with pytest.raises(PdfUnavailable, match="не готов"):
        _converter(lambda request: httpx.Response(503)).check()


# ── прикладной слой ───────────────────────────────────────────────────────────

def test_unconfigured_service_is_none_with_hint(monkeypatch):
    monkeypatch.setattr(documents.settings, "gotenberg_url", "")
    documents.set_pdf_converter(None)
    assert documents.pdf_mode() == "none"
    pdf, how = documents.docx_to_pdf(b"PK")
    assert pdf is None and "GOTENBERG_URL" in how
    assert "GOTENBERG_URL" in documents.pdf_unavailable_detail(how)


def test_configured_service_builds_pdf():
    fake = _Fake()
    documents.set_pdf_converter(fake)
    assert documents.pdf_mode() == "gotenberg" and documents.pdf_error() == ""
    assert documents.docx_to_pdf(b"PK", "a.pdf") == (PDF, "gotenberg")
    assert fake.converted == ["a.pdf"]


def test_unhealthy_service_is_none_and_health_is_cached():
    fake = _Fake(check_error="сервис PDF не отвечает.")
    documents.set_pdf_converter(fake)
    assert documents.pdf_mode() == "none"
    assert documents.pdf_error() == "сервис PDF не отвечает."
    assert fake.checks == 1, "готовность не должна проверяться на каждый вызов"


def test_conversion_failure_returns_reason():
    class Broken(_Fake):
        def convert(self, docx, filename):
            raise PdfUnavailable("сервис PDF вернул ошибку 500.")

    documents.set_pdf_converter(Broken())
    assert documents.docx_to_pdf(b"PK") == (None, "сервис PDF вернул ошибку 500.")


# ── эндпоинты ─────────────────────────────────────────────────────────────────

def test_schedule_pdf_endpoint_returns_pdf(admin_client):
    documents.set_pdf_converter(_Fake())
    today = dt.date.today()
    r = admin_client.get("/api/schedule/pdf", params={"year": today.year, "month": today.month})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf" and r.content == PDF


def test_schedule_pdf_endpoint_explains_when_service_is_down(admin_client):
    class Down(_Fake):
        def convert(self, docx, filename):
            raise PdfUnavailable("сервис PDF не отвечает (ConnectError).")

    documents.set_pdf_converter(Down())
    today = dt.date.today()
    r = admin_client.get("/api/schedule/pdf", params={"year": today.year, "month": today.month})
    assert r.status_code == 501
    assert "ConnectError" in r.json()["detail"] and "GOTENBERG_URL" in r.json()["detail"]


# ── настоящий Gotenberg (CI; локально — если контейнер запущен) ──────────────

@pytest.mark.skipif(not os.environ.get("GOTENBERG_URL"), reason="GOTENBERG_URL не задан")
def test_real_gotenberg_converts_cyrillic_document():
    from pypdf import PdfReader

    documents.set_pdf_converter(GotenbergConverter(os.environ["GOTENBERG_URL"], timeout=60))
    docx = write_docx(Document([text("Ночной отчёт"), Table(
        [[TCell((text("Пункт"),)), TCell((text("ОК"),))]], widths_mm=(60, 20))]))
    pdf, how = documents.docx_to_pdf(docx, "probe.pdf")
    assert pdf is not None and how == "gotenberg", how
    assert "Ночной отчёт" in PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
