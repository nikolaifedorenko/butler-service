"""Экран «Настройки → Чаты и Почта»: параметры доставки, проверки каналов, шаблоны сообщений,
журнал отправок.

Секреты наружу не отдаются: в ответах — маска и признак «задано», в аудит пишутся имена
изменённых ключей, а не значения. Обращение к сети идёт вне транзакции; отказ бота или
почтового сервера — ``UpstreamError``.
"""
from __future__ import annotations

import re
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import transaction, transactional
from app.core.errors import Conflict, NotFound, Rejected, UpstreamError
from app.core.time import local_now
from app.modules.exchange.application.tables import raw, write_csv

from ..adapters.orm import NotifyDispatch
from ..adapters.transports.email import send_mail, split_addresses
from ..adapters.transports.telegram import TelegramBot
from ..ports.transports import TransportError
from .chats import list_chats, refresh_chats
from .config import load_config, public_config, save_config
from .dispatch import claim, deliver_row, dispatch_dict, journal_of
from .templates import DEFAULT_TEMPLATES, DOMAIN_TITLES, PLACEHOLDERS, render_template, save_template, template_of

SECURITY_MODES = ["none", "starttls", "ssl"]

# образцы значений для предпросмотра шаблона: видно, как подставятся плейсхолдеры
SAMPLE_CONTEXT = {
    "date": "19.10.2026",
    "shift": "Ночная смена 20:00–08:00",
    "service": "Техническая служба",
    "items": "1. Вилла 4003 · Освещение: все лампы горят — мигает лампа у входа\n"
             "2. Вилла 4007 · Витражи закрыты",
    "duty": "Иванов И.И., Петрова А.С.",
    "author": "Громова Е.П.",
    "time": "02:48",
    "car": "7",
}

CSV_HEADER = ["Время", "Раздел", "Кто отправил", "Получатель", "Канал", "Адрес", "Тема", "Позиций", "Вложений",
              "Статус", "Ошибок доставки", "Попыток", "Внешний id", "Состав отправки"]


# ─────────────────────────── параметры доставки ───────────────────────────

def config_view(db: Session) -> dict:
    """Параметры доставки с маскированными секретами, готовность каналов и каталог чатов."""
    return {"config": public_config(load_config(db)), "chats": list_chats(db),
            "domains": dict(DOMAIN_TITLES), "security_modes": list(SECURITY_MODES)}


@transactional
def save(db: Session, principal: Principal, values: dict) -> dict:
    """Сохранить параметры доставки; пустое значение секрета — «не менять»."""
    try:
        changed = save_config(db, values)["changed"]
    except ValueError as exc:
        raise Rejected(str(exc)) from exc
    audit(db, principal, "notify_config_update", "notify", {"changed": changed})
    db.flush()
    return {"changed": changed, "config": public_config(load_config(db))}


# ─────────────────────────── проверки каналов ───────────────────────────

def check_bot(db: Session, principal: Principal, token: str = "") -> dict:
    """Проверить токен бота — сохранённый или ещё не сохранённый. Запрос уходит только на
    настроенный адрес Bot API: адрес из запроса увёл бы токен на чужой сервер."""
    cfg = load_config(db)
    try:
        me = TelegramBot(token.strip() or cfg.telegram_token, cfg.telegram_api, cfg.timeout).get_me()
    except TransportError as exc:
        raise UpstreamError(str(exc)) from exc
    with transaction(db):
        audit(db, principal, "notify_telegram_check", "notify", {"username": me.get("username", "")})
    return {"username": me.get("username", ""), "first_name": me.get("first_name", ""), "id": me.get("id")}


@transactional
def refresh_chat_catalog(db: Session, principal: Principal) -> dict:
    """Обновить каталог чатов из обновлений бота. Чат появляется, когда бота добавили в
    группу и в ней написали хотя бы одно сообщение."""
    try:
        result = refresh_chats(db, load_config(db))
    except TransportError as exc:
        raise UpstreamError(str(exc)) from exc
    audit(db, principal, "notify_chats_refresh", "notify", {"added": result["added"], "seen": result["seen"]})
    return result


def send_test_message(db: Session, principal: Principal, chat_id: int, text: str = "") -> int:
    """Тестовое сообщение в чат: проверка, что бот добавлен и пишет. Возвращает id сообщения."""
    cfg = load_config(db)
    text = text.strip() or (f"Тестовое сообщение butler-service · {local_now():%d.%m.%Y %H:%M}\n"
                            "Если вы видите это сообщение, бот настроен и добавлен в чат.")
    try:
        message_id = TelegramBot(cfg.telegram_token, cfg.telegram_api, cfg.timeout).send_message(chat_id, text)
    except TransportError as exc:
        raise UpstreamError(str(exc)) from exc
    with transaction(db):
        audit(db, principal, "notify_telegram_test", f"chat:{chat_id}", {"ok": bool(message_id)})
    return message_id


def send_test_email(db: Session, principal: Principal, to: str, subject: str = "") -> str:
    """Тестовое письмо: проверка почтового сервера, отправителя и адреса. Возвращает Message-ID."""
    cfg = load_config(db)
    recipients = split_addresses(to)
    if not recipients:
        raise Rejected("Укажите корректный адрес получателя")
    body = (f"Это тестовое письмо системы учёта butler-service.\n"
            f"Отправлено: {local_now():%d.%m.%Y %H:%M}.\n"
            f"Отправитель: {cfg.email_from}\nСервер: {cfg.smtp_host}:{cfg.smtp_port} "
            f"({cfg.smtp_security}).\n\nЕсли письмо пришло, доставка почты настроена.")
    try:
        message_id = send_mail(cfg, to=recipients, subject=subject.strip() or "Тестовое письмо butler-service",
                               body=body, require_all_recipients=True)
    except TransportError as exc:
        raise UpstreamError(str(exc)) from exc
    with transaction(db):
        audit(db, principal, "notify_email_test", f"email:{to}", {"message_id": message_id})
    return message_id


# ─────────────────────────── шаблоны сообщений ───────────────────────────

def _domain(domain: str) -> str:
    if domain not in DOMAIN_TITLES:
        raise NotFound("Неизвестный раздел уведомлений")
    return domain


def unknown_placeholders(domain: str, text: str) -> list[str]:
    """Плейсхолдеры, которых нет у раздела: опечатка ловится при сохранении, а не при отправке."""
    known = {p.strip("{}") for p in PLACEHOLDERS.get(domain, [])}
    return sorted(set(re.findall(r"\{([a-z_]+)\}", text or "")) - known)


@transactional
def save_template_text(db: Session, principal: Principal, domain: str, text: str) -> dict:
    """Сохранить шаблон раздела; пустой текст возвращает вариант по умолчанию."""
    _domain(domain)
    unknown = unknown_placeholders(domain, text)
    if unknown:
        raise Rejected(f"Неизвестные плейсхолдеры: {', '.join('{' + u + '}' for u in unknown)}. "
                       f"Доступны: {', '.join(PLACEHOLDERS[domain])}")
    try:
        save_template(db, domain, text)
    except ValueError as exc:
        raise Rejected(str(exc)) from exc
    clean = text.strip()
    audit(db, principal, "notify_template_update", f"domain:{domain}",
          {"chars": len(clean), "customized": bool(clean)})
    return {"domain": domain, "text": template_of(db, domain),
            "customized": bool(clean and clean != DEFAULT_TEMPLATES[domain])}


def preview_template(domain: str, text: str) -> str:
    """Шаблон на образцовых данных — тем же рендером, что при отправке."""
    _domain(domain)
    return render_template(text.strip() or DEFAULT_TEMPLATES[domain], SAMPLE_CONTEXT)


# ─────────────────────────── журнал отправок ───────────────────────────

def export_csv(db: Session, domain: str = "", limit: int = 2000) -> bytes:
    """Общий журнал отправок в CSV — всех разделов или одного. Состав отправки хранится
    снимком, поэтому выгрузка прошлой смены со временем не меняется."""
    if domain:
        rows = journal_of(db, domain, None, limit=limit)
    else:
        rows = list(db.scalars(select(NotifyDispatch).order_by(NotifyDispatch.ts.desc(), NotifyDispatch.id.desc())
                               .limit(max(1, min(limit, 20000)))))
    lines = []
    for row in rows:
        d = dispatch_dict(row)
        items = "; ".join(f"{i.get('area') or '—'} · {i.get('text') or ''}"
                          + (f" ({i.get('comment')})" if i.get("comment") else "") for i in d["items"])
        # адрес и внешний id законно начинаются с «-», «+», «@» (id чата, телефон, имя канала):
        # они пишутся как есть, без защиты от формул
        lines.append([d["ts"] or "", d["domain"], d["actor_name"], d["recipient_name"], d["channel_title"],
                      raw(d["target"]), d["subject"], d["items_count"], d["media_count"], d["status_title"],
                      d["error"], d["attempts"], raw(d["external_id"]), items])
    return write_csv(CSV_HEADER, lines)


def resend(db: Session, principal: Principal, dispatch_id: int) -> dict:
    """Повторить неудачную доставку тем же текстом и составом. Строка журнала берётся в
    отправку до обращения к сети, поэтому двойной повтор второй раз не отправит."""
    row: Optional[NotifyDispatch] = db.get(NotifyDispatch, dispatch_id)
    if row is None:
        raise NotFound("Запись журнала не найдена")
    if row.status != "failed" or not claim(db, row.id, "failed"):
        raise Conflict("Эта доставка уже отправлена или отправляется")
    with transaction(db):
        try:
            deliver_row(db, row, cfg=load_config(db))
        except TransportError as exc:
            raise UpstreamError(str(exc)) from exc
        audit(db, principal, "notify_dispatch_resend", f"dispatch:{row.id}",
              {"domain": row.domain, "channel": row.channel, "attempts": row.attempts, "status": row.status})
    return dispatch_dict(row)
