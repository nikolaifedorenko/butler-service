"""Учётные данные и параметры транспорта доставки (общие для всего приложения).

Хранятся в обычной таблице ``settings`` рядом с правилами объекта, но это СЕКРЕТЫ:
в БД — зашифрованными ключом NOTIFY_SECRET_KEY (secrets.py, 25.10.2026), в API —
маскированными (``public_config``), в журналах и аудите не печатаются вовсе. Пустое значение секрета при сохранении означает «не менять» —
иначе интерфейс, который не показывает токен, стирал бы его при каждом сохранении.

Почта — через MS Exchange (решение владельца): либо релей без авторизации
(user/password пустые), либо SMTP AUTH; позже возможен Graph/EWS — тогда здесь
появятся client_id/tenant, а транспорт останется за тем же интерфейсом.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.settings_store import Setting

from .secrets import decrypt, encrypt

# ключ → (значение по умолчанию, секрет?, подпись для интерфейса)
NOTIFY_KEYS: dict[str, tuple[str, bool, str]] = {
    "notify_telegram_token": ("", True, "Токен бота (BotFather)"),
    "notify_telegram_api": ("https://api.telegram.org", False,
                            "Адрес Bot API (меняют при работе через корпоративный прокси)"),
    "notify_smtp_host": ("", False, "Сервер SMTP или коннектор MS Exchange"),
    "notify_smtp_port": ("587", False, "Порт SMTP"),
    "notify_smtp_security": ("starttls", False, "Без шифрования / STARTTLS / SSL"),
    "notify_smtp_user": ("", False, "Пользователь (пусто — релей без авторизации)"),
    "notify_smtp_password": ("", True, "Пароль SMTP"),
    "notify_email_from": ("", False, "Адрес отправителя (должен быть разрешён коннектором)"),
    "notify_email_reply_to": ("", False, "Адрес для ответа (необязательно)"),
    "notify_timeout": ("20", False, "Таймаут отправки, секунд"),
}

SECRET_KEYS = frozenset(k for k, (_, secret, _) in NOTIFY_KEYS.items() if secret)
SMTP_SECURITY = ("none", "starttls", "ssl")


def mask_secret(value: str) -> str:
    """Маска секрета: видно только последние 4 символа (и что значение задано)."""
    if not value:
        return ""
    return "•" * 8 + value[-4:]


@dataclass
class NotifyConfig:
    """Параметры транспорта. Секреты — внутри процесса, наружу только маски."""

    telegram_token: str = ""
    telegram_api: str = "https://api.telegram.org"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_security: str = "starttls"
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = ""
    email_reply_to: str = ""
    timeout: int = 20
    # секреты, которые не расшифровались (ключ потерян или сменился) — ввести заново
    unreadable: tuple[str, ...] = ()

    @property
    def telegram_ready(self) -> bool:
        return bool(self.telegram_token.strip())

    @property
    def email_ready(self) -> bool:
        """Достаточно ли данных для письма: сервер и разрешённый отправитель."""
        return bool(self.smtp_host.strip() and self.email_from.strip())


def load_config(db: Session) -> NotifyConfig:
    """Собрать параметры доставки из настроек объекта (отсутствующие — по умолчанию)."""
    rows = {s.key: s.value for s in db.scalars(select(Setting)
                                               .where(Setting.key.in_(list(NOTIFY_KEYS))))}
    values = {k: rows.get(k, default) or default for k, (default, _, _) in NOTIFY_KEYS.items()}
    unreadable = []
    for key in SECRET_KEYS:
        values[key], ok = decrypt(values[key])
        if not ok:
            unreadable.append(key)
    return NotifyConfig(
        telegram_token=values["notify_telegram_token"].strip(),
        telegram_api=(settings.notify_telegram_api.strip() or values["notify_telegram_api"].strip()
                      or "https://api.telegram.org").rstrip("/"),
        smtp_host=values["notify_smtp_host"].strip(),
        smtp_port=_int(values["notify_smtp_port"], 587, 1, 65535),
        smtp_security=values["notify_smtp_security"] if values["notify_smtp_security"] in SMTP_SECURITY
        else "starttls",
        smtp_user=values["notify_smtp_user"].strip(),
        smtp_password=values["notify_smtp_password"],
        email_from=values["notify_email_from"].strip(),
        email_reply_to=values["notify_email_reply_to"].strip(),
        timeout=_int(values["notify_timeout"], 20, 1, 300),
        unreadable=tuple(sorted(unreadable)),
    )


def public_config(cfg: NotifyConfig) -> dict:
    """Параметры для интерфейса: секреты маскированы + признак «заполнено»."""
    return {
        "telegram": {
            "token_set": cfg.telegram_ready,
            "token_masked": mask_secret(cfg.telegram_token),
            "api": cfg.telegram_api,
        },
        "email": {
            "host": cfg.smtp_host, "port": cfg.smtp_port, "security": cfg.smtp_security,
            "user": cfg.smtp_user, "password_set": bool(cfg.smtp_password),
            "password_masked": mask_secret(cfg.smtp_password),
            "from": cfg.email_from, "reply_to": cfg.email_reply_to,
        },
        "timeout": cfg.timeout,
        "ready": {"telegram": cfg.telegram_ready, "email": cfg.email_ready},
        # не расшифровались (ключ потерян или сменился) — интерфейс просит ввести заново
        "unreadable": list(cfg.unreadable),
    }


def save_config(db: Session, values: dict, *, allow_secrets: bool = True) -> dict:
    """Сохранить параметры доставки. Возвращает список реально изменённых ключей.

    Секрет с пустым значением не трогаем («не менять»): интерфейс не показывает
    токен, поэтому пустое поле означает «оставить прежним». Очистить секрет можно
    явным значением "clear" — иначе убрать забытый токен было бы невозможно.
    """
    # SEC-03: куда уходят токен бота и пароль SMTP — не меняется из интерфейса незаметно
    cur = load_config(db)
    api = str(values.get("notify_telegram_api") or "").strip().rstrip("/")
    if api and api != cur.telegram_api:
        raise ValueError("Адрес Bot API задаётся переменной окружения NOTIFY_TELEGRAM_API "
                         "(защита токена бота)")
    moved = any(values.get(k) is not None and str(values[k]).strip() != v
                for k, v in (("notify_smtp_host", cur.smtp_host), ("notify_smtp_user", cur.smtp_user)))
    if moved and cur.smtp_password and not str(values.get("notify_smtp_password") or ""):
        raise ValueError("Сменился сервер или пользователь SMTP — введите пароль заново: "
                         "сохранённый пароль не отправляется на новый адрес")
    changed: list[str] = []
    for key, (default, secret, _title) in NOTIFY_KEYS.items():
        if key not in values:
            continue
        raw = values[key]
        if raw is None:
            continue
        new = str(raw).strip() if key != "notify_smtp_password" else str(raw)
        if secret:
            if not allow_secrets:
                continue
            if new == "":
                continue                      # «не менять»
            if new == "clear":
                new = ""                      # явная очистка секрета
            else:
                new = encrypt(new)            # в БД — только шифротекст (SecretKeyMissing без ключа)
        if key == "notify_smtp_security" and new not in SMTP_SECURITY:
            raise ValueError("Режим шифрования: none, starttls или ssl")
        if key in ("notify_smtp_port", "notify_timeout"):
            low, high = (1, 65535) if key == "notify_smtp_port" else (1, 300)
            port = _int(new, _int(default, low, low, high), low, high)
            new = str(port)
        row = db.get(Setting, key)
        if row is None:
            if new == default:
                continue                      # значение по умолчанию можно не хранить
            db.add(Setting(key=key, value=new))
        elif row.value != new:
            row.value = new
        else:
            continue
        changed.append(key)
    if changed:
        db.flush()
    return {"changed": changed}


def _int(value, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(float(value))))
    except (TypeError, ValueError):
        return default
