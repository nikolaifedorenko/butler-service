"""Общий слой доставки уведомлений: Telegram и почта (этап 4, 19.10.2026).

Решение владельца: отправка сообщений — общая функциональность приложения, а не
принадлежность ночного отчёта. Позже к доставке подключат электрокары (замечания
при возврате), График и Табель (заявления, закрытие периода), отметки (опоздания).

Как устроен пакет
-----------------
``config``      учётные данные и параметры транспорта (ключи в таблице settings,
                в API отдаются маскированными);
``templates``   шаблоны сообщений ПО РАЗДЕЛАМ и подстановка плейсхолдеров;
``transports``  Telegram Bot API и SMTP/MS Exchange — единственные места, где
                приложение выходит в сеть;
``chats``       общий каталог чатов Telegram (getUpdates) — справочник получателей;
``dispatch``    отправка и общий журнал (NotifyDispatch) — этап 5;
``recipients``  порт «кто получает»: правило задаёт раздел, а не этот пакет.

Пакет НЕ знает про ночной отчёт: раздел передаёт сюда готовый текст, получателей
и вложения. Тесты подменяют ``sender``/``mailer`` (см. transports), поэтому прогон
не выходит в интернет.
"""
from __future__ import annotations

from .config import (
    NOTIFY_KEYS,
    NotifyConfig,
    load_config,
    mask_secret,
    public_config,
    save_config,
)
from .templates import (
    DEFAULT_TEMPLATES,
    DOMAIN_TITLES,
    PLACEHOLDERS,
    render_template,
    template_of,
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
