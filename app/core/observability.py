"""Наблюдаемость и защита транспорта: middleware request-id/лога/метрик,
CSRF (double-submit cookie), заголовки безопасности и CSP (ядро, R5).

Перенесено из app/main.py в фазе C1 (20.10.2026, EXECUTION-SPEC-v2 §2):
main.py остаётся composition root — создаёт FastAPI, вызывает register(app)
и подключает роутеры. Порядок регистрации middleware сохранён (снизу вверх:
csrf_protection → security_headers → request_context; последний — самый внешний,
поэтому X-Request-ID и заголовки безопасности попадают и на 403-ответы CSRF).
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
import secrets
import time
import uuid

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from .config import settings
from .security import new_csrf_token

# ── CSRF: double-submit cookie (ADR-0004) ────────────────────────────────────
_CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# Вход — точка входа: CSRF-cookie у клиента ещё нет, и это отдельная поверхность атаки
# (login-CSRF), поэтому его не проверяем (оба варианта: JSON и form-login с редиректом
# для менеджеров паролей). Остальные mutating-запросы требуют заголовок.
_CSRF_EXEMPT_PATHS = {"/api/auth/login", "/api/auth/login-form"}


def _set_csrf_cookie(response, token: str) -> None:
    response.set_cookie(settings.csrf_cookie_name, token, httponly=False,
                        samesite="lax", path="/", secure=settings.cookie_secure)


async def csrf_protection(request: Request, call_next):
    """CSRF-защита по схеме double-submit cookie.

    Сессия живёт в httponly-cookie (JS её не видит); CSRF-токен — в отдельной cookie,
    которую JS читает и передаёт в заголовке X-CSRF-Token. Кросс-сайтовый запрос не
    сможет прочитать cookie другого origin, поэтому подделать пару «cookie+заголовок»
    нельзя.

    Токен проверяется ДО вызова обработчика: отклонённый запрос не должен производить
    побочных эффектов. (Проверка после call_next лишь подменяла ответ — действие к
    этому моменту уже было совершено и закоммичено в БД.) Заголовок сравнивается
    побайтово: compare_digest для str с не-ASCII символами бросает TypeError,
    а значение заголовка приходит из сети.
    """
    if not settings.csrf_enabled:
        return await call_next(request)
    token = request.cookies.get(settings.csrf_cookie_name)
    fresh_cookie = token is None
    if fresh_cookie:
        token = new_csrf_token()
    if request.method not in _CSRF_SAFE_METHODS and request.url.path not in _CSRF_EXEMPT_PATHS:
        header = request.headers.get("x-csrf-token", "")
        header_b = header.encode("utf-8", "surrogateescape")
        if fresh_cookie or not header_b or not secrets.compare_digest(header_b, token.encode()):
            # на 403 тоже выдаём cookie: клиент обновится и повторит запрос уже с токеном
            denied = JSONResponse(
                {"detail": "CSRF-проверка не пройдена: обновите страницу и повторите"},
                status_code=403)
            _set_csrf_cookie(denied, token)
            return denied
    response = await call_next(request)
    if fresh_cookie:
        _set_csrf_cookie(response, token)
    return response


# ── заголовки безопасности и CSP (ADR-0004) ──────────────────────────────────
# Политика CSP подобрана по фактическому содержимому интерфейса: все скрипты —
# внешние файлы (inline-скриптов и onclick-обработчиков в SPA нет — проверено),
# поэтому script-src строго 'self'. Inline-атрибуты style="…" в шаблонах есть
# (300+) — для них 'unsafe-inline' в style-src (осознанный компромисс без сборки;
# см. docs/adr/0004). data: — SVG-фавикон и иконки селекторов в CSS; blob: —
# скачивание PDF/DOCX через createObjectURL; frame-ancestors дублирует X-Frame-Options.
_CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; "
        "worker-src 'self'; manifest-src 'self'; object-src 'none'; base-uri 'self'; "
        "form-action 'self'; frame-ancestors 'none'")


async def security_headers(request: Request, call_next):
    response = await call_next(request)
    h = response.headers
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Referrer-Policy", "same-origin")
    h.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=(), payment=()")
    csp_header = "Content-Security-Policy-Report-Only" if settings.csp_report_only \
        else "Content-Security-Policy"
    h.setdefault(csp_header, _CSP)
    # HSTS имеет смысл только по TLS: за прокси смотрим X-Forwarded-Proto
    # (доверяем ему лишь при TRUST_PROXY_HEADERS — иначе заголовок клиентский),
    # без прокси — схему запроса. По HTTP заголовок браузерами игнорируется,
    # но не рассылаем его зря.
    proto = (request.headers.get("x-forwarded-proto", "") if settings.trust_proxy_headers
             else "") or request.url.scheme
    if proto == "https":
        h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if request.url.path.startswith("/api/") and "cache-control" not in h:
        h["Cache-Control"] = "no-store"   # персональные данные не должны оседать в кэшах
    return response


# ── наблюдаемость: request-id, JSON-лог запросов, метрики Prometheus ──────────
# Метрики — опциональная зависимость: без prometheus_client приложение работает,
# METRICS_ENABLED просто не включить (в requirements.txt пакет есть).
try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

    _HTTP_COUNT = Counter("tt_http_requests_total", "HTTP-запросы по маршрутам",
                          ["method", "route", "status"])
    _HTTP_LATENCY = Histogram("tt_http_request_duration_seconds",
                              "Латентность HTTP-запросов, с", ["method", "route"])
    _PROM_OK = True
except ImportError:          # pragma: no cover - зависит от окружения
    _PROM_OK = False

_access_log = logging.getLogger("butler.access")
if settings.log_json and not _access_log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(message)s"))
    _access_log.addHandler(_h)
    _access_log.setLevel(logging.INFO)
    _access_log.propagate = False

# health опрашивается healthcheck'ами каждые секунды, /metrics — скрейпером:
# в логе запросов это шум без информации
_QUIET_LOG_PATHS = {"/api/health", "/metrics"}
_REQUEST_ID_RE = re.compile(r"[^A-Za-z0-9._-]")


def _observe(request: Request, status: int, started: float, request_id: str) -> None:
    duration_ms = round((time.perf_counter() - started) * 1000.0, 1)
    # метка маршрута — шаблон из роутера (/api/employees/{employee_id}), а не сырой
    # путь: иначе случайные 404-URL раздули бы кардинальность метрик
    label = getattr(request.scope.get("route"), "path", None) or "unmatched"
    if settings.metrics_enabled and _PROM_OK:
        try:
            _HTTP_COUNT.labels(request.method, label, status).inc()
            _HTTP_LATENCY.labels(request.method, label).observe(duration_ms / 1000.0)
        except Exception:   # метрики не должны ронять запрос
            pass
    if settings.log_json and request.url.path not in _QUIET_LOG_PATHS:
        _access_log.info(json.dumps({
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"),
            "method": request.method, "path": request.url.path, "status": status,
            "duration_ms": duration_ms, "route": label, "request_id": request_id,
            "ip": request.client.host if request.client else "-",
        }, ensure_ascii=False))


async def request_context(request: Request, call_next):
    """Сквозной request-id (от прокси или сгенерированный) + учёт для лога/метрик.

    X-Request-ID возвращается в ответе: по нему один запрос связывается между
    логом приложения, логом прокси и обращением пользователя в поддержку.
    """
    incoming = request.headers.get("x-request-id", "")
    request_id = _REQUEST_ID_RE.sub("", incoming)[:64] or uuid.uuid4().hex[:16]
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        _observe(request, 500, started, request_id)
        raise
    _observe(request, response.status_code, started, request_id)
    response.headers["X-Request-ID"] = request_id
    return response


def metrics_endpoint():
    """Prometheus-метрики. Включаются METRICS_ENABLED=1; по умолчанию 404 —
    счётчики не должны быть публичными (за прокси доступ можно ограничить по IP)."""
    if not settings.metrics_enabled or not _PROM_OK:
        raise HTTPException(status_code=404, detail="Not found")
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


def register(app: FastAPI) -> None:
    """Подключает middleware и /metrics к приложению (composition root вызывает).

    Порядок add — как прежний порядок декораторов в main.py (снизу вверх:
    csrf → security_headers → request_context; последний становится внешним).
    """
    app.middleware("http")(csrf_protection)
    app.middleware("http")(security_headers)
    app.middleware("http")(request_context)
    app.add_api_route("/metrics", metrics_endpoint, include_in_schema=False, methods=["GET"])
