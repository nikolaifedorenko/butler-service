"""Шифрование секретов уведомлений в БД (решение владельца 25.10.2026, строгие требования ИБ).

Токен Telegram-бота и пароль SMTP лежали в таблице settings открытым текстом: кто получил
копию базы или бэкап, получал и их (рецензия аудита 22.10.2026). Теперь в БД — только
шифротекст Fernet (AES-128-CBC + HMAC-SHA256, библиотека cryptography/PyCA) с префиксом
``enc:v1:``; ключ — переменная окружения NOTIFY_SECRET_KEY, в базе и бэкапах его нет.

* Смена ключа: NOTIFY_SECRET_KEY="новый,старый" — новый шифрует, оба расшифровывают; при
  старте значения перешифровываются новым, после этого старый из окружения можно убрать.
* Ключ потерян или не подходит: секрет считается незаданным, интерфейс просит ввести его
  заново (``unreadable``) — доставка не падает, а честно «не настроена».
* Без ключа секрет не сохранить: ошибка с подсказкой, как сгенерировать ключ.
* Секреты, сохранённые до шифрования, при старте шифруются (encrypt_stored_secrets).

Ключ генерируется командой::

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
from __future__ import annotations

import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.settings_store import Setting

PREFIX = "enc:v1:"
KEYGEN_HINT = ('python -c "from cryptography.fernet import Fernet; '
               'print(Fernet.generate_key().decode())"')
_log = logging.getLogger("uvicorn.error")


class SecretKeyMissing(ValueError):
    """Секрет не сохранить: NOTIFY_SECRET_KEY не задан."""


def _keys() -> list[str]:
    return [k.strip() for k in (settings.notify_secret_key or "").split(",") if k.strip()]


def check_key_config() -> None:
    """Ключ задан, но не разбирается — отказ на старте, а не 500 на первом обращении."""
    for i, key in enumerate(_keys(), 1):
        try:
            Fernet(key)
        except (ValueError, TypeError) as exc:
            raise RuntimeError(
                f"NOTIFY_SECRET_KEY: ключ №{i} не ключ Fernet ({exc}). Сгенерируйте: {KEYGEN_HINT}"
            ) from exc


def _fernet() -> Optional[MultiFernet]:
    keys = _keys()
    return MultiFernet([Fernet(k) for k in keys]) if keys else None


def is_encrypted(stored: str) -> bool:
    return (stored or "").startswith(PREFIX)


def encrypt(value: str) -> str:
    f = _fernet()
    if f is None:
        raise SecretKeyMissing(
            "Секреты уведомлений хранятся зашифрованными: задайте NOTIFY_SECRET_KEY в окружении "
            f"приложения (.env) и перезапустите его. Ключ: {KEYGEN_HINT}")
    return PREFIX + f.encrypt(value.encode()).decode()


def decrypt(stored: str) -> tuple[str, bool]:
    """(значение, прочитано ли). Незашифрованное (до 25.10.2026) — как есть; ключа нет или
    не подходит — ("", False): секрет считается незаданным, его вводят заново."""
    if not is_encrypted(stored):
        return stored or "", True
    f = _fernet()
    if f is None:
        return "", False
    try:
        return f.decrypt(stored[len(PREFIX):].encode()).decode(), True
    except InvalidToken:
        return "", False


def encrypt_stored_secrets(db: Session, keys) -> int:
    """При старте: открытые секреты → шифротекст, зашифрованные старым ключом → новым.
    Без NOTIFY_SECRET_KEY открытые секреты остаются (доставка не ломается) — с предупреждением."""
    rows = [r for r in db.scalars(select(Setting).where(Setting.key.in_(list(keys)))) if r.value]
    plain = [r for r in rows if not is_encrypted(r.value)]
    f = _fernet()
    if f is None:
        if plain:
            _log.warning("NOTIFY_SECRET_KEY не задан: секреты уведомлений (%s) лежат в БД открытым "
                         "текстом. Задайте ключ — при следующем старте они зашифруются. Ключ: %s",
                         ", ".join(r.key for r in plain), KEYGEN_HINT)
        return 0
    changed = 0
    for row in rows:
        if not is_encrypted(row.value):
            row.value = encrypt(row.value)
        else:
            try:
                row.value = PREFIX + f.rotate(row.value[len(PREFIX):].encode()).decode()
            except InvalidToken:
                _log.warning("Секрет %s не расшифровывается текущим NOTIFY_SECRET_KEY — "
                             "введите его заново в «Настройки → Чаты и Почта»", row.key)
                continue
        changed += 1
    if changed:
        db.flush()
    return changed
