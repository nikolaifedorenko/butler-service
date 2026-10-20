"""Общий каталог чатов Telegram (этап 4).

Список чатов не вводится руками: бота добавляют в группы служб, пишут в группе
хотя бы одно сообщение — и чат появляется в каталоге после «Обновить список чатов»
(getUpdates). Закрепление чата за службой делается в карточке службы
(ResponsibilityService.chat_ids): один и тот же чат может быть получателем
недостатков ночного обхода и замечаний по электрокарам.

Каталог хранится в БД (notify_chats), поэтому интерфейс показывает названия и
последнюю активность даже тогда, когда Telegram недоступен.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import now_local

from ..adapters.orm import NotifyChat
from ..adapters.transports.telegram import TelegramBot
from .config import NotifyConfig

# из каких полей обновления Telegram достаём чат (личные сообщения, группы, каналы)
_CHAT_SOURCES = ("message", "edited_message", "channel_post", "edited_channel_post",
                 "my_chat_member", "chat_member")


def chats_from_updates(updates: list[dict]) -> list[dict]:
    """Уникальные чаты из ответа getUpdates (порядок — как встретились)."""
    out: dict[int, dict] = {}
    for upd in updates or []:
        if not isinstance(upd, dict):
            continue
        for key in _CHAT_SOURCES:
            payload = upd.get(key)
            if not isinstance(payload, dict):
                continue
            chat = payload.get("chat")
            if not isinstance(chat, dict):
                continue
            cid = chat.get("id")
            if not isinstance(cid, int):
                continue
            row = out.setdefault(cid, {"chat_id": cid, "title": "", "username": "",
                                       "kind": chat.get("type") or "group"})
            # название: у групп title, у людей — имя/фамилия, у канала — title
            title = chat.get("title") or " ".join(
                str(chat.get(p) or "") for p in ("first_name", "last_name")).strip()
            if title:
                row["title"] = title
            if chat.get("username"):
                row["username"] = str(chat["username"])
            break
    return list(out.values())


def chat_dict(c: NotifyChat, *, used_by: Optional[list[str]] = None) -> dict:
    return {
        "id": c.id, "chat_id": c.chat_id, "title": c.title or f"чат {c.chat_id}",
        "username": c.username or "", "kind": c.kind or "group",
        "first_seen": c.first_seen.isoformat(timespec="seconds") if c.first_seen else None,
        "last_seen": c.last_seen.isoformat(timespec="seconds") if c.last_seen else None,
        "used_by": used_by or [],
    }


def list_chats(db: Session) -> list[dict]:
    """Каталог чатов + какие службы их используют (видно, кому чат уже закреплён)."""
    import json

    from ..adapters.orm import ResponsibilityService

    usage: dict[int, list[str]] = {}
    for svc in db.scalars(select(ResponsibilityService)):
        try:
            ids = json.loads(svc.chat_ids or "[]")
        except ValueError:
            ids = []
        for cid in ids if isinstance(ids, list) else []:
            usage.setdefault(int(cid), []).append(svc.name)
    rows = db.scalars(select(NotifyChat).order_by(NotifyChat.title, NotifyChat.chat_id))
    return [chat_dict(c, used_by=usage.get(c.chat_id, [])) for c in rows]


def refresh_chats(db: Session, cfg: NotifyConfig, *, bot: Optional[TelegramBot] = None) -> dict:
    """Обновить каталог: getUpdates → новые чаты добавить, у известных обновить название.

    Обновления НЕ подтверждаются offset'ом: приложение не обрабатывает команды бота,
    а Telegram хранит последние обновления сутки — повторное обновление каталога
    видит те же чаты и ничего не ломает.
    """
    client = bot or TelegramBot(cfg.telegram_token, cfg.telegram_api, cfg.timeout)
    updates = client.get_updates()
    found = chats_from_updates(updates)
    known = {c.chat_id: c for c in db.scalars(select(NotifyChat))}
    ts = now_local()
    added = 0
    for row in found:
        existing = known.get(row["chat_id"])
        if existing is None:
            db.add(NotifyChat(chat_id=row["chat_id"], title=row["title"],
                              username=row["username"], kind=row["kind"],
                              first_seen=ts, last_seen=ts))
            added += 1
        else:
            existing.title = row["title"] or existing.title
            existing.username = row["username"] or existing.username
            existing.kind = row["kind"] or existing.kind
            existing.last_seen = ts
    db.flush()
    return {"added": added, "seen": len(found), "total": len(known) + added,
            "chats": list_chats(db)}
