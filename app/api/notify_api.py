"""API общих настроек доставки: /api/notify/* (этап 4).

Экран «Настройки → Чаты и Почта»: учётные данные Telegram и MS Exchange, общий
каталог чатов, шаблоны сообщений по разделам и проверки («Проверить бота»,
«Тестовое письмо»). Настройки общие для всего приложения — разделы подключаются
к доставке со своими шаблонами и получателями.

Права: чтение и правка параметров — ``settings.edit`` (администратор и менеджер
объекта: здесь токены и пароли); каталог чатов доступен и старшему батлеру
(``require_manager``) — он закрепляет чаты за службами в справочнике ночного обхода.

Секреты наружу не отдаются: в ответах только маска и признак «значение задано»,
в аудит пишутся имена изменённых ключей, а не их значения.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import Principal, audit, require_manager
from ..db import get_db
from ..deps import now_local
from ..notify.chats import list_chats, refresh_chats
from ..notify.config import load_config, public_config, save_config
from ..notify.templates import (
    DEFAULT_TEMPLATES,
    DOMAIN_TITLES,
    PLACEHOLDERS,
    render_template,
    save_template,
    template_of,
    templates_payload,
)
from ..notify.transports import TransportError
from ..notify.transports.email import send_mail, split_addresses
from ..notify.transports.telegram import TelegramBot
from ..permissions import require_perm

router = APIRouter(prefix="/api/notify", tags=["notify"])

EDIT = require_perm("settings.edit")

# образцы значений для предпросмотра шаблона: видно, как подставятся плейсхолдеры
SAMPLE_CTX = {
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


class ConfigIn(BaseModel):
    """Параметры доставки. Пустая строка у секрета означает «не менять»."""

    notify_telegram_token: Optional[str] = None
    notify_telegram_api: Optional[str] = None
    notify_smtp_host: Optional[str] = None
    notify_smtp_port: Optional[str] = None
    notify_smtp_security: Optional[str] = None
    notify_smtp_user: Optional[str] = None
    notify_smtp_password: Optional[str] = None
    notify_email_from: Optional[str] = None
    notify_email_reply_to: Optional[str] = None
    notify_timeout: Optional[str] = None


class TelegramCheckIn(BaseModel):
    token: str = ""          # не пустой — проверить ещё не сохранённый токен
    api: str = ""


class TelegramTestIn(BaseModel):
    chat_id: int
    text: str = ""


class EmailTestIn(BaseModel):
    to: str
    subject: str = ""


class TemplateIn(BaseModel):
    text: str = ""


@router.get("/config")
def get_config(principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    """Параметры доставки (секреты маскированы) + готовность каналов и каталог чатов."""
    cfg = load_config(db)
    return {"config": public_config(cfg), "chats": list_chats(db),
            "domains": DOMAIN_TITLES, "security_modes": ["none", "starttls", "ssl"]}


@router.put("/config")
def put_config(payload: ConfigIn, principal: Principal = Depends(EDIT),
               db: Session = Depends(get_db)):
    """Сохранить параметры доставки. В аудит попадают имена ключей, не значения."""
    values = {k: v for k, v in payload.model_dump().items() if v is not None}
    try:
        res = save_config(db, values)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit(db, principal, "notify_config_update", "notify", {"changed": res["changed"]})
    db.commit()
    cfg = load_config(db)
    return {"ok": True, "changed": res["changed"], "config": public_config(cfg)}


@router.post("/telegram/check")
def telegram_check(payload: TelegramCheckIn, principal: Principal = Depends(EDIT),
                   db: Session = Depends(get_db)):
    """getMe: проверить токен (можно ещё не сохранённый) и увидеть username бота."""
    cfg = load_config(db)
    token = payload.token.strip() or cfg.telegram_token
    api = payload.api.strip() or cfg.telegram_api
    try:
        me = TelegramBot(token, api, cfg.timeout).get_me()
    except TransportError as e:
        raise HTTPException(status_code=502, detail=str(e))
    audit(db, principal, "notify_telegram_check", "notify", {"username": me.get("username", "")})
    db.commit()
    return {"ok": True, "bot": {"username": me.get("username", ""),
                                "first_name": me.get("first_name", ""),
                                "id": me.get("id")}}


@router.post("/telegram/chats")
def telegram_chats(principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    """Обновить общий каталог чатов (getUpdates).

    Бот должен быть добавлен в группы служб, и в группе должно появиться хотя бы
    одно сообщение — иначе Telegram не отдаст чат в обновлениях.
    """
    cfg = load_config(db)
    try:
        res = refresh_chats(db, cfg)
    except TransportError as e:
        raise HTTPException(status_code=502, detail=str(e))
    audit(db, principal, "notify_chats_refresh", "notify",
          {"added": res["added"], "seen": res["seen"]})
    db.commit()
    return {"ok": True, **res}


@router.get("/chats")
def get_chats(principal: Principal = Depends(require_manager), db: Session = Depends(get_db)):
    """Каталог чатов для карточки службы: какие чаты найдены и кем уже используются."""
    return {"chats": list_chats(db)}


@router.post("/telegram/test")
def telegram_test(payload: TelegramTestIn, principal: Principal = Depends(EDIT),
                  db: Session = Depends(get_db)):
    """Тестовое сообщение в выбранный чат — проверка, что бот добавлен и пишет."""
    cfg = load_config(db)
    text = payload.text.strip() or (
        f"Тестовое сообщение butler-service · {now_local():%d.%m.%Y %H:%M}\n"
        "Если вы видите это сообщение, бот настроен и добавлен в чат.")
    try:
        message_id = TelegramBot(cfg.telegram_token, cfg.telegram_api, cfg.timeout) \
            .send_message(payload.chat_id, text)
    except TransportError as e:
        raise HTTPException(status_code=502, detail=str(e))
    audit(db, principal, "notify_telegram_test", f"chat:{payload.chat_id}", {"ok": bool(message_id)})
    db.commit()
    return {"ok": True, "message_id": message_id}


@router.post("/email/test")
def email_test(payload: EmailTestIn, principal: Principal = Depends(EDIT),
               db: Session = Depends(get_db)):
    """Тестовое письмо: проверяет коннектор Exchange, отправителя и адрес получателя."""
    cfg = load_config(db)
    to = split_addresses(payload.to)
    if not to:
        raise HTTPException(status_code=400, detail="Укажите корректный адрес получателя")
    subject = payload.subject.strip() or "Тестовое письмо butler-service"
    body = (f"Это тестовое письмо системы учёта butler-service.\n"
            f"Отправлено: {now_local():%d.%m.%Y %H:%M}.\n"
            f"Отправитель: {cfg.email_from}\nСервер: {cfg.smtp_host}:{cfg.smtp_port} "
            f"({cfg.smtp_security}).\n\nЕсли письмо пришло, доставка почты настроена.")
    try:
        message_id = send_mail(cfg, to=to, subject=subject, body=body)
    except TransportError as e:
        raise HTTPException(status_code=502, detail=str(e))
    audit(db, principal, "notify_email_test", f"email:{payload.to}", {"message_id": message_id})
    db.commit()
    return {"ok": True, "message_id": message_id}


@router.get("/dispatches")
def list_dispatches(domain: str = "", limit: int = 100,
                    principal: Principal = Depends(require_manager),
                    db: Session = Depends(get_db)):
    """Общий журнал отправок приложения (фильтр по разделу).

    История не редактируется: видно, какой раздел, кто, кому и что отправил,
    статус доставки и ошибку. Журнал доступен менеджменту; в разделе «Ночной
    отчёт» есть своя обёртка /api/night/reports/{id}/dispatches для батлеров.
    """
    from ..notify.dispatch import dispatch_dict, journal_of

    rows = journal_of(db, domain, None, limit=limit) if domain else []
    if not domain:
        from sqlalchemy import select as _select

        from ..models import NotifyDispatch
        rows = list(db.scalars(_select(NotifyDispatch)
                               .order_by(NotifyDispatch.ts.desc(), NotifyDispatch.id.desc())
                               .limit(max(1, min(limit, 500)))))
    return {"dispatches": [dispatch_dict(d) for d in rows]}


@router.post("/dispatches/{dispatch_id}/resend")
def resend_dispatch(dispatch_id: int, principal: Principal = Depends(require_manager),
                    db: Session = Depends(get_db)):
    """Повторить неудачную доставку тем же текстом и составом (журнал не переписывается)."""
    from ..models import NotifyDispatch
    from ..notify.config import load_config
    from ..notify.dispatch import dispatch_dict, resend

    row = db.get(NotifyDispatch, dispatch_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Запись журнала не найдена")
    if row.status == "sent":
        raise HTTPException(status_code=409, detail="Эта доставка уже отправлена")
    try:
        resend(db, row, cfg=load_config(db))
    except TransportError as e:
        raise HTTPException(status_code=502, detail=str(e))
    audit(db, principal, "notify_dispatch_resend", f"dispatch:{row.id}",
          {"domain": row.domain, "channel": row.channel, "attempts": row.attempts,
           "status": row.status})
    db.commit()
    return {"ok": True, "dispatch": dispatch_dict(row)}


@router.get("/templates")
def get_templates(principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    """Шаблоны сообщений по разделам (свои у каждого раздела приложения)."""
    return {"templates": templates_payload(db)}


@router.put("/templates/{domain}")
def put_template(domain: str, payload: TemplateIn, principal: Principal = Depends(EDIT),
                 db: Session = Depends(get_db)):
    """Сохранить шаблон раздела. Пустой текст — вернуть вариант по умолчанию."""
    if domain not in DOMAIN_TITLES:
        raise HTTPException(status_code=404, detail="Неизвестный раздел уведомлений")
    text = payload.text
    unknown = _unknown_placeholders(domain, text)
    if unknown:
        raise HTTPException(status_code=400,
                            detail=f"Неизвестные плейсхолдеры: "
                                   f"{', '.join('{' + u + '}' for u in unknown)}. "
                                   f"Доступны: {', '.join(PLACEHOLDERS[domain])}")
    try:
        save_template(db, domain, text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit(db, principal, "notify_template_update", f"domain:{domain}",
          {"chars": len(text.strip()), "customized": bool(text.strip())})
    db.commit()
    return {"ok": True, "domain": domain, "text": template_of(db, domain),
            "customized": bool(text.strip() and text.strip() != DEFAULT_TEMPLATES[domain])}


@router.post("/templates/{domain}/preview")
def preview_template(domain: str, payload: TemplateIn, principal: Principal = Depends(EDIT)):
    """Предпросмотр: тот же рендер, что при отправке, но на образцовых данных."""
    if domain not in DOMAIN_TITLES:
        raise HTTPException(status_code=404, detail="Неизвестный раздел уведомлений")
    text = payload.text.strip() or DEFAULT_TEMPLATES[domain]
    return {"ok": True, "text": render_template(text, SAMPLE_CTX)}


def _unknown_placeholders(domain: str, text: str) -> list[str]:
    """Плейсхолдеры, которых нет у раздела: опечатку ловим до отправки, не после."""
    import re

    known = {p.strip("{}") for p in PLACEHOLDERS.get(domain, [])}
    found = set(re.findall(r"\{([a-z_]+)\}", text or ""))
    return sorted(found - known)
