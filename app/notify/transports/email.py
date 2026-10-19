"""Транспорт почты: SMTP / коннектор MS Exchange (этап 4).

Приложение позже включат в домен, поэтому поддерживаются оба варианта подключения
к Exchange:
  * ``security="none"``, пустые user/password — релей без авторизации
    (коннектор разрешает отправку с адреса приложения);
  * ``security="starttls"`` (порт 587) или ``"ssl"`` (465) + user/password — SMTP AUTH;
  * позже Graph/EWS — добавится третий транспорт за тем же интерфейсом send_mail().

Письмо собирается стандартным EmailMessage: текстовое тело (шаблон раздела),
вложения (фото/видео отметок) и Message-ID, который пишется в общий журнал
отправок как external_id — по нему письмо находится в почтовом логе Exchange.

``mailer`` подменяется в тестах: прогон не подключается к реальному серверу.
"""
from __future__ import annotations

import contextlib
import mimetypes
import smtplib
import uuid
from email.message import EmailMessage
from email.utils import formatdate
from typing import Callable, Optional, Sequence

from . import TransportError

# (cfg, message) → None
Mailer = Callable[[object, EmailMessage], None]


def smtp_mailer(cfg, msg: EmailMessage) -> None:
    """Отправитель по умолчанию: smtplib из стандартной библиотеки."""
    try:
        if cfg.smtp_security == "ssl":
            server = smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=cfg.timeout)
        else:
            server = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=cfg.timeout)
    except (OSError, smtplib.SMTPException) as e:
        raise TransportError(f"Почтовый сервер недоступен: {type(e).__name__}") from e
    try:
        if cfg.smtp_security == "starttls":
            server.starttls()
        if cfg.smtp_user:
            server.login(cfg.smtp_user, cfg.smtp_password)
        server.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        raise TransportError("Почтовый сервер отклонил авторизацию (SMTP AUTH)") from e
    except smtplib.SMTPRecipientsRefused as e:
        raise TransportError(f"Сервер не принял получателя: {e.recipients}") from e
    except smtplib.SMTPSenderRefused as e:
        raise TransportError("Сервер отклонил адрес отправителя (проверьте разрешённый "
                             "адрес в коннекторе Exchange)") from e
    except (OSError, smtplib.SMTPException) as e:
        raise TransportError(f"Ошибка отправки письма: {type(e).__name__}") from e
    finally:
        with contextlib.suppress(OSError, smtplib.SMTPException):
            server.quit()


def build_message(cfg, *, to: Sequence[str], cc: Sequence[str] = (), subject: str,
                  body: str, attachments: Sequence[tuple[str, bytes, str]] = ()) -> EmailMessage:
    """Собрать письмо: получатели, тема, текст, вложения, Message-ID."""
    if not to:
        raise TransportError("Не указан получатель письма")
    if "@" not in (cfg.email_from or ""):
        raise TransportError("Не задан адрес отправителя (Настройки → Чаты и Почта)")
    msg = EmailMessage()
    msg["From"] = cfg.email_from
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject or "Уведомление butler-service"
    msg["Date"] = formatdate(localtime=True)
    # свой Message-ID (а не make_msgid с fqdn машины): по нему письмо находится
    # в почтовом логе Exchange и в общем журнале отправок (external_id)
    msg["Message-ID"] = f"<{uuid.uuid4().hex}@butler-service>"
    msg.set_content(body or "")
    for name, blob, mime in attachments:
        maintype, subtype = _mime_parts(mime, name)
        msg.add_attachment(blob or b"", maintype=maintype, subtype=subtype,
                           filename=name or f"file.{subtype}")
    return msg


def _mime_parts(mime: str, name: str) -> tuple[str, str]:
    mime = (mime or "").strip()
    if "/" in mime:
        maintype, _, subtype = mime.partition("/")
        return maintype, subtype or "octet-stream"
    guessed = mimetypes.guess_type(name or "")[0] or "application/octet-stream"
    maintype, _, subtype = guessed.partition("/")
    return maintype, subtype or "octet-stream"


def send_mail(cfg, *, to: Sequence[str], cc: Sequence[str] = (), subject: str, body: str,
              attachments: Sequence[tuple[str, bytes, str]] = (),
              mailer: Optional[Mailer] = None) -> str:
    """Отправить письмо. Возвращает Message-ID (пишется в журнал как external_id)."""
    if not (cfg.smtp_host or "").strip():
        raise TransportError("Почтовый сервер не задан (Настройки → Чаты и Почта)")
    msg = build_message(cfg, to=to, cc=cc, subject=subject, body=body, attachments=attachments)
    (mailer or smtp_mailer)(cfg, msg)
    return str(msg["Message-ID"] or "")


def split_addresses(raw: str) -> list[str]:
    """Список адресов из строки: разделители — запятая, точка с запятой, пробел."""
    import re

    parts = [p.strip().strip("<>") for p in re.split(r"[,;\s]+", raw or "") if p.strip()]
    return [p for p in parts if "@" in p]
