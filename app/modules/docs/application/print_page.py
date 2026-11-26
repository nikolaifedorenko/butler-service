"""Сборка страницы печати (чистый HTML для окна печати заявлений и Графика).

Прежняя печать собирала документ строкой на клиенте и писала его в about:blank
вместе с inline-скриптом автопечати: окно наследует CSP страницы приложения,
а ``script-src 'self'`` блокирует inline-скрипты — кнопки «Печать» молча не
работали (A1, аудит 25.10.2026). Страницу собирает сервер: тот же шаблон стилей,
скрипт автопечати — внешний файл из SHELL (разрешён CSP), исполнение — во
фрейме на странице приложения. Тело и дополнительные стили клиент собирает
шаблонами lit-html: данные приходят уже экранированными, здесь они вставляются
как есть; заголовок страницы экранируется здесь.
"""
from __future__ import annotations

from html import escape

from app.core.schemas import ApiModel

PRINT_MEDIA_TYPE = "text/html; charset=utf-8"

_BASE_CSS = """
  @page { size: A4 landscape; margin: 10mm; }
  body { font-family: -apple-system, 'Segoe UI', Roboto, Arial, sans-serif; color: #1a2438; font-size: 11px; }
  h1 { font-size: 16px; margin: 0 0 2mm; }
  table { border-collapse: collapse; width: 100%; }
  th, td { border: 1px solid #b9c2d0; padding: 1.2mm 1mm; text-align: center; font-size: 9px; }
  th.name, td.name { text-align: left; padding-left: 2mm; width: 52mm; font-size: 10px; }
  tr.group td { background: #eef2f8; font-weight: 700; text-align: left; padding-left: 2mm; font-size: 10px; }
  .muted { color: #8b98ad; }
"""


class PrintIn(ApiModel):
    """Тело запроса на страницу печати: собранный клиентом HTML и его стили."""

    title: str = ""
    body: str
    css: str = ""


def print_page(payload: PrintIn) -> str:
    """Полный документ страницы печати: базовые стили печати + стили раздела,
    скрипт автопечати — внешний (CSP страницы приложения запрещает inline)."""
    return (f"<!doctype html><html><head><meta charset=\"utf-8\">"
            f"<title>{escape(payload.title)}</title>"
            f"<style>{_BASE_CSS}\n{payload.css}</style>"
            f"<script src=\"/static/js/print-page.js?v=2026-11-26-family-links\" defer></script>"
            f"</head><body>{payload.body}</body></html>")
