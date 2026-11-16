"""API экрана «Настройки → Чаты и Почта»: /api/notify/*.

Параметры доставки, проверки бота и почты, шаблоны сообщений и общий журнал отправок.
Настройки общие для приложения; разделы подключаются к доставке со своими шаблонами.

Права: ``settings.edit`` — здесь токены и пароли. Каталог чатов доступен и с правом
``night.edit``: по нему закрепляют чаты за службами ночного обхода.
Правила — в ``application/settings.py``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm
from app.modules.exchange.application.tables import CSV_MEDIA_TYPE, attachment

from ..application import settings
from ..application.chats import list_chats
from ..application.templates import templates_payload
from .schemas import (
    BotCheckedOut,
    ChatsOut,
    ChatsRefreshedOut,
    ConfigIn,
    ConfigOut,
    ConfigSavedOut,
    DispatchResentOut,
    EmailSentOut,
    EmailTestIn,
    MessageSentOut,
    TelegramCheckIn,
    TelegramTestIn,
    TemplateIn,
    TemplatePreviewOut,
    TemplateSavedOut,
    TemplatesOut,
)

router = APIRouter(prefix="/api/notify", tags=["notify"])

EDIT = require_perm("settings.edit")


@router.get("/config", response_model=ConfigOut)
def get_config(principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    """Параметры доставки (секреты маскированы), готовность каналов и каталог чатов."""
    return settings.config_view(db)


@router.put("/config", response_model=ConfigSavedOut)
def put_config(payload: ConfigIn, principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    """Сохранить параметры доставки."""
    return settings.save(db, principal, {k: v for k, v in payload.model_dump().items() if v is not None})


@router.post("/telegram/check", response_model=BotCheckedOut)
def telegram_check(payload: TelegramCheckIn, principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    """Проверить токен бота (можно ещё не сохранённый) и увидеть имя бота."""
    return {"bot": settings.check_bot(db, principal, payload.token)}


@router.post("/telegram/chats", response_model=ChatsRefreshedOut)
def telegram_chats(principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    """Обновить общий каталог чатов."""
    return settings.refresh_chat_catalog(db, principal)


@router.get("/chats", response_model=ChatsOut)
def get_chats(principal: Principal = Depends(require_perm("settings.edit", "night.edit")),
              db: Session = Depends(get_db)):
    """Каталог чатов для карточки службы: какие чаты найдены и кем уже используются."""
    return {"chats": list_chats(db)}


@router.post("/telegram/test", response_model=MessageSentOut)
def telegram_test(payload: TelegramTestIn, principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    """Тестовое сообщение в выбранный чат."""
    return {"message_id": settings.send_test_message(db, principal, payload.chat_id, payload.text)}


@router.post("/email/test", response_model=EmailSentOut)
def email_test(payload: EmailTestIn, principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    """Тестовое письмо."""
    return {"message_id": settings.send_test_email(db, principal, payload.to, payload.subject)}


@router.get("/dispatches/export.csv", response_class=Response)
def export_dispatches_csv(domain: str = "", limit: int = 2000, principal: Principal = Depends(EDIT),
                          db: Session = Depends(get_db)):
    """Общий журнал отправок в CSV — всех разделов или одного (domain)."""
    return Response(content=settings.export_csv(db, domain, limit), media_type=CSV_MEDIA_TYPE,
                    headers=attachment("notify-dispatches.csv"))


@router.post("/dispatches/{dispatch_id}/resend", response_model=DispatchResentOut)
def resend_dispatch(dispatch_id: int, principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    """Повторить неудачную доставку тем же текстом и составом."""
    return {"dispatch": settings.resend(db, principal, dispatch_id)}


@router.get("/templates", response_model=TemplatesOut)
def get_templates(principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    """Шаблоны сообщений по разделам."""
    return {"templates": templates_payload(db)}


@router.put("/templates/{domain}", response_model=TemplateSavedOut)
def put_template(domain: str, payload: TemplateIn, principal: Principal = Depends(EDIT),
                 db: Session = Depends(get_db)):
    """Сохранить шаблон раздела; пустой текст возвращает вариант по умолчанию."""
    return settings.save_template_text(db, principal, domain, payload.text)


@router.post("/templates/{domain}/preview", response_model=TemplatePreviewOut)
def preview_template(domain: str, payload: TemplateIn, principal: Principal = Depends(EDIT)):
    """Предпросмотр шаблона на образцовых данных."""
    return {"text": settings.preview_template(domain, payload.text)}
