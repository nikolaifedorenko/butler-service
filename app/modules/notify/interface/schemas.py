"""Модели запросов и ответов экрана «Настройки → Чаты и Почта»."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.core.schemas import ApiModel

from ..application.schemas import DispatchOut

# ── запросы ──────────────────────────────────────────────────────────────────


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


class TelegramTestIn(BaseModel):
    chat_id: int
    text: str = ""


class EmailTestIn(BaseModel):
    to: str
    subject: str = ""


class TemplateIn(BaseModel):
    text: str = ""


# ── ответы ───────────────────────────────────────────────────────────────────


class TelegramConfigOut(ApiModel):
    token_set: bool
    token_masked: str           # сам токен наружу не отдаётся
    api: str


class EmailConfigOut(ApiModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    host: str
    port: int
    security: str
    user: str
    password_set: bool
    password_masked: str        # сам пароль наружу не отдаётся
    sender: str = Field(alias="from")
    reply_to: str


class ChannelsReadyOut(ApiModel):
    telegram: bool
    email: bool


class PublicConfigOut(ApiModel):
    telegram: TelegramConfigOut
    email: EmailConfigOut
    timeout: int
    ready: ChannelsReadyOut
    unreadable: list[str]       # секреты, которые не расшифровались: их нужно ввести заново


class ChatOut(ApiModel):
    id: int
    chat_id: int
    title: str
    username: str
    kind: str
    first_seen: Optional[str]
    last_seen: Optional[str]
    used_by: list[str]          # службы, за которыми чат закреплён


class ConfigOut(ApiModel):
    config: PublicConfigOut
    chats: list[ChatOut]
    domains: dict[str, str]     # разделы приложения, у которых свой шаблон сообщения
    security_modes: list[str]


class ConfigSavedOut(ApiModel):
    ok: bool = True
    changed: list[str]          # имена изменённых параметров
    config: PublicConfigOut


class BotOut(ApiModel):
    username: str
    first_name: str
    id: Optional[int]


class BotCheckedOut(ApiModel):
    ok: bool = True
    bot: BotOut


class ChatsRefreshedOut(ApiModel):
    ok: bool = True
    added: int
    seen: int
    total: int
    chats: list[ChatOut]


class ChatsOut(ApiModel):
    chats: list[ChatOut]


class MessageSentOut(ApiModel):
    ok: bool = True
    message_id: int             # id сообщения в Telegram


class EmailSentOut(ApiModel):
    ok: bool = True
    message_id: str             # Message-ID письма


class DispatchResentOut(ApiModel):
    ok: bool = True
    dispatch: DispatchOut


class TemplateOut(ApiModel):
    domain: str
    title: str
    text: str
    default: str
    customized: bool
    placeholders: list[str]


class TemplatesOut(ApiModel):
    templates: list[TemplateOut]


class TemplateSavedOut(ApiModel):
    ok: bool = True
    domain: str
    text: str
    customized: bool


class TemplatePreviewOut(ApiModel):
    ok: bool = True
    text: str
