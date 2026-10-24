"""Адрес клиента — одно место для лимита входа и журнала запросов."""
from __future__ import annotations

import ipaddress

from .config import settings


def _valid_ip(value: str) -> str | None:
    """Канонический IP либо None. Зона IPv6 («%eth0») — не часть адреса; «%» и «_»
    иначе попали бы в LIKE лимита входа, а длинная строка — в ключ String(80)."""
    try:
        return str(ipaddress.ip_address(value.strip().split("%", 1)[0]))
    except ValueError:
        return None


def client_ip(request) -> str:
    """Без reverse-proxy адрес клиента — адрес соединения. За прокси это адрес прокси
    (все клиенты в одном бакете лимита), поэтому X-Forwarded-For читается ТОЛЬКО
    при TRUST_PROXY_HEADERS=1 — включайте, когда приложение гарантированно стоит
    за своим доверенным прокси (nginx из docker-compose.prod.yml), иначе заголовок
    подделывается клиентом и лимит обходится/направляется на чужой IP.

    Правый адрес дописал наш nginx ($proxy_add_x_forwarded_for); левые присылает клиент —
    по ним лимит обходился сменой заголовка (аудит 21.10.2026, SEC-01). Сам uvicorn
    заголовки прокси не разбирает (--no-proxy-headers): с --forwarded-allow-ips "*" он
    подставлял ЛЕВЫЙ адрес, и при TRUST_PROXY_HEADERS=0 обход возвращался (22.10.2026)."""
    peer = request.client.host if request.client else "unknown"
    if settings.trust_proxy_headers:
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            ip = _valid_ip(xff.split(",")[-1])
            if ip:
                return ip
    return _valid_ip(peer) or peer[:45]
