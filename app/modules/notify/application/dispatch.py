"""Отправка и общий журнал (этап 5).

Правила отправки (решения владельца от 19.10.2026):
  * отправка ТОЛЬКО вручную — никакой автоотправки при закрытии объекта или смены;
  * отправка — право night.dispatch (по умолчанию у всех ролей); отправленное помечается;
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

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from sqlalchemy import select, update
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

# Outbox (аудит 22.10.2026, CONC-02): строка журнала пишется ДО сети —
# queued → sending → sent | failed. Падение процесса не теряет отправку и не дублирует её.
QUEUED, SENDING = "queued", "sending"
STATUS_TITLES = {QUEUED: "в очереди", SENDING: "отправляется", "sent": "отправлено", "failed": "ошибка"}
# одна доставка не идёт дольше: таймаут канала ≤ 300 с, у Telegram — до двух запросов
STALE_SENDING = dt.timedelta(minutes=30)
UNKNOWN_DELIVERY = ("Статус доставки неизвестен: отправку прервал перезапуск сервера. "
                    "Проверьте у получателя, прежде чем повторять")


@dataclass
class Attachment:
    """Вложение — путь к файлу, а не байты (PERF-04): Telegram получает файл потоком с диска,
    письмо читает его только при сборке. Раньше все вложения рассылки (до 10 видео по 50 МБ)
    читались в память заранее."""
    name: str
    path: Path
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
        out.append(Attachment(name=photo.filename or path.name, path=path, mime=mime))
    return out


def _email_parts(attachments: Sequence[Attachment]) -> list[tuple[str, bytes, str]]:
    """Письмо собирается целиком в памяти (base64) — читаем файлы только здесь; пропавший
    после выборки файл пропускаем, как и раньше."""
    out = []
    for a in attachments:
        try:
            out.append((a.name, a.path.read_bytes(), a.mime))
        except OSError:
            continue
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
        files = [(a.name, a.path, a.mime) for a in attachments]
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
                         attachments=_email_parts(attachments),
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
        "status": d.status, "status_title": STATUS_TITLES.get(d.status, d.status),
        "error": d.error or "", "external_id": d.external_id or "",
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


def queue_group(db: Session, *, domain: str, ref_id: int, actor_id: Optional[int],
                actor_name: str, group: dict, message: str, subject: str = "") -> list[NotifyDispatch]:
    """Поставить сообщения группы недостатков в очередь (outbox): по строке журнала на
    доставку, status=queued, без сети. Отправляет run_outbox() после commit очереди.

    Каналы службы независимы: чат и письмо уходят оба, если включены (решение
    владельца). Сбой одного канала не отменяет другой — статус пишется по каждой
    доставке отдельно.
    """
    snapshot = json.dumps([{"id": d["id"], "area": d.get("area"), "text": d.get("text"),
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
            # снимок копии — повтор отправляет тем же составом (P1 20.10.2026)
            cc_json=json.dumps(list(cc)),
            items_json=snapshot, media_json=json.dumps(media_ids),
            media_count=len(media_ids), status=QUEUED, attempts=0)
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def claim(db: Session, row_id: int, from_status: str) -> bool:
    """Взять строку журнала в отправку: from_status → sending одним UPDATE и commit ДО сети.
    Второй отправитель (двойной повтор, фоновая доотправка, другой воркер) получит False."""
    taken = db.execute(update(NotifyDispatch)
                       .where(NotifyDispatch.id == row_id, NotifyDispatch.status == from_status)
                       .values(status=SENDING, sending_at=now_local())
                       .execution_options(synchronize_session=False)).rowcount
    db.commit()
    return taken == 1


def deliver_row(db: Session, row: NotifyDispatch, *, cfg: Optional[NotifyConfig] = None,
                bot=None, mailer=None) -> NotifyDispatch:
    """Доставить строку журнала, взятую claim(): текст, копия и вложения — из её снимка.
    Первая отправка и ручной повтор идут одним путём (журнал не переписываем)."""
    from .config import load_config

    conf = cfg or load_config(db)
    try:
        media_ids = json.loads(row.media_json or "[]")
    except ValueError:
        media_ids = []
    attachments = attachments_of(db, media_ids)
    # Копия письма — из снимка строки журнала (cc_json, P1 20.10.2026): раньше
    # повторная отправка теряла адресатов копии.
    # У строк, сохранённых до миграции, cc_json пуст — повторят отправку без
    # копии, как и прежде (снимка нет — восстановить его неоткуда).
    try:
        cc = tuple(json.loads(row.cc_json or "[]"))
    except ValueError:
        cc = ()
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


def run_outbox(db: Session, *, ids: Optional[Sequence[int]] = None,
               cfg: Optional[NotifyConfig] = None, bot=None, mailer=None) -> list[NotifyDispatch]:
    """Отправить очередь: строки ids — сразу из запроса, без ids — все queued (фоновая
    доотправка, bootstrap/night_sync). Каждая строка коммитится дважды: sending до сети
    и sent | failed после — повторно её не возьмёт никто."""
    from .config import load_config

    q = select(NotifyDispatch).where(NotifyDispatch.status == QUEUED)
    if ids is not None:
        q = q.where(NotifyDispatch.id.in_(list(ids)))
    rows = list(db.scalars(q.order_by(NotifyDispatch.id)))
    conf = (cfg or load_config(db)) if rows else None
    done: list[NotifyDispatch] = []
    for row in rows:
        if claim(db, row.id, QUEUED):
            deliver_row(db, row, cfg=conf, bot=bot, mailer=mailer)
            db.commit()
            done.append(row)
    return done


def fail_stale_sending(db: Session) -> int:
    """Строки, застрявшие в sending (процесс упал посреди доставки): дошло ли сообщение —
    неизвестно. Автоматически не повторяем — дубль службе хуже; помечаем ошибкой, чтобы
    повторить вручную после проверки."""
    n = db.execute(update(NotifyDispatch)
                   .where(NotifyDispatch.status == SENDING,
                          NotifyDispatch.sending_at < now_local() - STALE_SENDING)
                   .values(status="failed", error=UNKNOWN_DELIVERY,
                           attempts=NotifyDispatch.attempts + 1)
                   .execution_options(synchronize_session=False)).rowcount
    db.commit()
    return n
