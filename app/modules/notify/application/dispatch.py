"""Отправка и общий журнал (этап 5).

Правила отправки (решения владельца от 19.10.2026):
  * отправка ТОЛЬКО вручную — никакой автоотправки при закрытии объекта или смены;
  * отправить может любой пользователь обхода; отправленное помечается;
  * всё скопом или выборочно (состав фиксируется в журнале снимком);
  * если недостаток исправили после отправки — ничего не отправляем повторно
    (ни «исправлено», ни отзыва сообщения);
  * общая служба у нескольких получателей не объединяется: каждая служба шлёт своё
    сообщение всем своим получателям.

Журнал ``notify_dispatches`` общий для всех разделов (domain + ref_id), поэтому
повторная отправка и экран журнала работают одинаково и для ночного отчёта, и для
любого раздела, который подключится позже.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.media import Photo
from app.core.time import now_local

from ..adapters.orm import NotifyDispatch
from ..adapters.transports.email import send_mail
from ..adapters.transports.telegram import TelegramBot
from ..ports.transports import TransportError
from .config import NotifyConfig

# Telegram-альбом ограничен 10 файлами; шлём поштучно, но без фанатизма —
# остальное упоминаем в тексте, чтобы сообщение не уезжало минутами.
MAX_FILES_PER_MESSAGE = 10

CHANNEL_TITLES = {"telegram": "чат Telegram", "email": "письмо"}


@dataclass
class Attachment:
    name: str
    blob: bytes
    mime: str


def attachments_of(db: Session, photo_ids: Sequence) -> list[Attachment]:
    """Файлы вложений из хранилища. Удалённые по сроку хранения пропускаем:
    сообщение уходит без них, а в журнале остаётся фактическое число вложений."""
    from app.core.media import ALLOWED_EXT, ALLOWED_VIDEO_EXT, BASE_DIR

    out: list[Attachment] = []
    for pid in photo_ids or []:
        try:
            photo = db.get(Photo, int(pid))
        except (TypeError, ValueError):
            continue
        if photo is None or not photo.path:
            continue
        path = BASE_DIR / photo.path
        if not path.is_file():
            continue
        ext = path.suffix.lower().lstrip(".")
        mime = ALLOWED_EXT.get(ext) or ALLOWED_VIDEO_EXT.get(ext) or "application/octet-stream"
        try:
            blob = path.read_bytes()
        except OSError:
            continue
        out.append(Attachment(name=photo.filename or path.name, blob=blob, mime=mime))
    return out


def deliver(*, cfg: NotifyConfig, channel: str, target: str, message: str,
            subject: str = "", attachments: Sequence[Attachment] = (),
            cc: Sequence[str] = (), bot: Optional[TelegramBot] = None,
            mailer=None) -> str:
    """Доставить одно сообщение одним каналом. Возвращает external_id.

    Транспорт можно подменить (bot/mailer) — так делают тесты: прогон не выходит
    в интернет. Ошибка доставки — TransportError с текстом для журнала.
    """
    if channel == "telegram":
        client = bot or TelegramBot(cfg.telegram_token, cfg.telegram_api, cfg.timeout)
        chat_id = int(target)
        files = [(a.name, a.blob, a.mime) for a in attachments]
        note = ""
        if len(files) > MAX_FILES_PER_MESSAGE:
            note = f"\n\n(вложений {len(files)}, отправлены первые {MAX_FILES_PER_MESSAGE})"
            files = files[:MAX_FILES_PER_MESSAGE]
        message_id = client.send_message(chat_id, message + note)
        if files:
            client.send_media(chat_id, files)
        return str(message_id or "")
    if channel == "email":
        return send_mail(cfg, to=[target], cc=list(cc or ()), subject=subject or "Уведомление",
                         body=message,
                         attachments=[(a.name, a.blob, a.mime) for a in attachments],
                         mailer=mailer)
    raise TransportError(f"Неизвестный канал доставки: {channel}")


def dispatch_dict(d: NotifyDispatch) -> dict:
    """Строка общего журнала для интерфейса."""
    try:
        items = json.loads(d.items_json or "[]")
    except ValueError:
        items = []
    return {
        "id": d.id, "domain": d.domain, "ref_id": d.ref_id,
        "ts": d.ts.isoformat(timespec="seconds") if d.ts else None,
        "actor_name": d.actor_name or "",
        "recipient_id": d.recipient_id, "recipient_name": d.recipient_name or "",
        "channel": d.channel, "channel_title": CHANNEL_TITLES.get(d.channel, d.channel),
        "target": d.target, "subject": d.subject or "", "message": d.message or "",
        "items": items, "items_count": len(items), "media_count": d.media_count,
        "status": d.status, "error": d.error or "", "external_id": d.external_id or "",
        "attempts": d.attempts or 1,
        "can_retry": d.status == "failed",
    }


def journal_of(db: Session, domain: str, ref_id: Optional[int] = None,
               limit: int = 200) -> list[NotifyDispatch]:
    """Строки общего журнала раздела (или всего приложения, если ref_id не задан)."""
    q = select(NotifyDispatch).where(NotifyDispatch.domain == domain)
    if ref_id is not None:
        q = q.where(NotifyDispatch.ref_id == ref_id)
    return list(db.scalars(q.order_by(NotifyDispatch.ts.desc(), NotifyDispatch.id.desc())
                           .limit(max(1, min(limit, 500)))))


def send_group(db: Session, *, domain: str, ref_id: int, actor_id: Optional[int],
               actor_name: str, group: dict, message: str, subject: str = "",
               attachments: Sequence[Attachment] = (), items_snapshot: Optional[list] = None,
               cfg: Optional[NotifyConfig] = None, bot=None, mailer=None) -> list[NotifyDispatch]:
    """Отправить группе недостатков всем её получателям: по строке журнала на доставку.

    Каналы службы независимы: чат и письмо уходят оба, если включены (решение
    владельца). Сбой одного канала не отменяет другой — статус пишется по каждой
    доставке отдельно.
    """
    from .config import load_config

    conf = cfg or load_config(db)
    snapshot = json.dumps(items_snapshot if items_snapshot is not None
                          else [{"id": d["id"], "area": d.get("area"), "text": d.get("text"),
                                 "comment": d.get("comment"), "kind": d.get("kind")}
                                for d in group.get("defects", []) if d.get("sendable")],
                          ensure_ascii=False)
    media_ids = [p["id"] for d in group.get("defects", []) if d.get("sendable")
                 for p in (d.get("media") or [])]
    rows: list[NotifyDispatch] = []

    targets: list[tuple[str, str, str, tuple]] = []      # (channel, target, subject, cc)
    if group.get("use_telegram") and group.get("chat_ids"):
        targets += [("telegram", str(cid), "", ()) for cid in group["chat_ids"]]
    if group.get("use_email") and group.get("email_to"):
        targets.append(("email", ", ".join(group["email_to"]), subject,
                        tuple(group.get("email_copy") or ())))

    for channel, target, subj, cc in targets:
        row = NotifyDispatch(
            domain=domain, ref_id=ref_id, ts=now_local(),
            actor_user_id=actor_id, actor_name=actor_name,
            recipient_id=group.get("service_id"), recipient_name=group.get("service_name") or "",
            channel=channel, target=target, subject=subj, message=message,
            items_json=snapshot, media_json=json.dumps(media_ids),
            media_count=len(attachments), attempts=1)
        try:
            row.external_id = deliver(cfg=conf, channel=channel, target=target, message=message,
                                      subject=subj, attachments=attachments, cc=cc,
                                      bot=bot, mailer=mailer)
            row.status = "sent"
            row.error = ""
        except (TransportError, ValueError) as e:
            row.status = "failed"
            row.error = str(e)[:2000]
        db.add(row)
        db.flush()
        rows.append(row)
    return rows


def resend(db: Session, row: NotifyDispatch, *, cfg: Optional[NotifyConfig] = None,
           bot=None, mailer=None) -> NotifyDispatch:
    """Повторить неудачную доставку тем же текстом и составом (журнал не переписываем)."""
    from .config import load_config

    conf = cfg or load_config(db)
    try:
        media_ids = json.loads(row.media_json or "[]")
    except ValueError:
        media_ids = []
    attachments = attachments_of(db, media_ids)
    cc: tuple = ()
    try:
        row.external_id = deliver(cfg=conf, channel=row.channel, target=row.target,
                                  message=row.message, subject=row.subject,
                                  attachments=attachments, cc=cc, bot=bot, mailer=mailer)
        row.status = "sent"
        row.error = ""
    except (TransportError, ValueError) as e:
        row.status = "failed"
        row.error = str(e)[:2000]
    row.attempts = (row.attempts or 0) + 1
    row.media_count = len(attachments)
    db.flush()
    return row
