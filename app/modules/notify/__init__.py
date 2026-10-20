"""Модуль notify — общий слой доставки уведомлений: Telegram и почта.

Решение владельца (19.10.2026): отправка сообщений — общая функциональность
приложения, а не принадлежность ночного отчёта. Раздел передаёт сюда готовый
текст, получателей и вложения; модуль НЕ знает про ночной отчёт.

Эталонный бизнес-модуль (EXECUTION-SPEC-v2, фаза 5 / C3), слои:
``domain/``       тексты разделов, плейсхолдеры, подстановка (чистые, R1);
``application/``  config (учётные данные транспорта), templates (переопределения
                  из БД), recipients (порт «кто получает»), chats (каталог чатов
                  Telegram, getUpdates), dispatch (отправка и общий журнал);
``ports/``        контракт сбоя доставки TransportError;
``adapters/``     orm.py (модели notify_*) и transports/ (Telegram Bot API,
                  SMTP/MS Exchange) — единственные места выхода в сеть и в БД;
``interface/``    роутер «Чаты и Почта» + журнал отправок.

Другие модули импортируют только ``application``/``ports`` (R3); этот файл —
публичная граница (R4). Тесты подменяют leaf-функции транспортов
(``adapters.transports.telegram.http_sender``, ``adapters.transports.email.smtp_mailer``),
поэтому прогон не выходит в интернет.
"""
from __future__ import annotations

from .application.config import (
    NOTIFY_KEYS,
    NotifyConfig,
    load_config,
    mask_secret,
    public_config,
    save_config,
)
from .application.templates import template_of
from .domain.templates import (
    DEFAULT_TEMPLATES,
    DOMAIN_TITLES,
    PLACEHOLDERS,
    render_template,
)

__all__ = [
    "DEFAULT_TEMPLATES",
    "DOMAIN_TITLES",
    "NOTIFY_KEYS",
    "PLACEHOLDERS",
    "NotifyConfig",
    "load_config",
    "mask_secret",
    "public_config",
    "render_template",
    "save_config",
    "template_of",
]
