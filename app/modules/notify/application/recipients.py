"""Порт «кто получает»: правило выбора получателей задаёт РАЗДЕЛ, не транспорт.

Ночной отчёт: недостатки группируются по ответственным службам, у каждой службы
свои каналы (чат Telegram и/или письмо) и свои получатели — закреплённые чаты из
общего каталога, ящик службы и копия. Другой раздел (электрокары, заявления)
подключит сюда своё правило, не трогая ни транспорт, ни журнал.

Здесь же собирается «почему отправить нельзя» (problems): служба отключена, канал
не выбран, чат не закреплён, не указан ящик. Интерфейс показывает эти причины до
отправки, чтобы супервайзер не гадал, почему письмо не ушло.
"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..adapters.orm import ResponsibilityService
from ..adapters.transports.email import split_addresses


def service_chat_ids(svc: ResponsibilityService) -> list[int]:
    """Закреплённые за службой чаты (id из общего каталога Telegram)."""
    try:
        raw = json.loads(svc.chat_ids or "[]")
    except ValueError:
        return []
    out = []
    for cid in raw if isinstance(raw, list) else []:
        try:
            out.append(int(cid))
        except (TypeError, ValueError):
            continue
    return out


def group_by_service(db: Session, rows: list[dict]) -> list[dict]:
    """Группы недостатков по службам: каналы, получатели, готовность, состав.

    Позиции без службы собираются в группу service_id=None («Без службы») и
    показываются отдельно: отправить их нельзя, пока пункт не закреплён за службой.
    """
    ids = {r.get("service_id") for r in rows if r.get("service_id")}
    svcs: dict[int, ResponsibilityService] = {}
    if ids:
        svcs = {s.id: s for s in db.scalars(
            select(ResponsibilityService).where(ResponsibilityService.id.in_(ids)))}

    groups: dict = {}
    for row in rows:
        sid = row.get("service_id")
        g = groups.get(sid)
        if g is None:
            svc = svcs.get(sid)
            chats = service_chat_ids(svc) if svc is not None else []
            to = split_addresses(svc.email_to) if svc is not None else []
            cc = split_addresses(svc.email_copy) if svc is not None else []
            problems: list[str] = []
            if svc is None:
                problems.append("служба не задана — закрепите её за пунктом чек-листа")
            else:
                if not svc.active:
                    problems.append("служба отключена")
                if not svc.use_telegram and not svc.use_email:
                    problems.append("у службы не выбран канал доставки")
                if svc.use_telegram and not chats:
                    problems.append("чат не закреплён (каталог — «Настройки → Чаты и Почта»)")
                if svc.use_email and not to:
                    problems.append("не указан почтовый ящик службы")
            g = groups[sid] = {
                "service_id": sid,
                "service_name": svc.name if svc is not None else "Без службы",
                "sort_order": svc.sort_order if svc is not None else 10 ** 6,
                "active": bool(svc.active) if svc is not None else False,
                "use_telegram": bool(svc.use_telegram) if svc is not None else False,
                "use_email": bool(svc.use_email) if svc is not None else False,
                "chat_ids": chats, "email_to": to, "email_copy": cc,
                "note": (svc.note or "") if svc is not None else "",
                "problems": problems,
                "defects": [],
            }
        g["defects"].append(row)

    out = sorted(groups.values(), key=lambda g: (g["sort_order"], g["service_name"]))
    for g in out:
        sendable = [d for d in g["defects"] if d.get("sendable")]
        g["sendable_count"] = len(sendable)
        g["counts"] = {
            "total": len(g["defects"]),
            "sendable": len(sendable),
            "bad": sum(1 for d in g["defects"] if d.get("kind") == "bad"),
            "unchecked": sum(1 for d in g["defects"] if d.get("kind") == "unchecked"),
            "dispatched": sum(1 for d in g["defects"] if d.get("dispatched")),
            "fixed_after_dispatch": sum(1 for d in g["defects"] if d.get("fixed_after_dispatch")),
        }
        # «готово к отправке»: есть что слать и есть куда
        g["ready"] = bool(sendable) and not g["problems"]
        g["channels"] = (["telegram"] if g["use_telegram"] and g["chat_ids"] else []) \
            + (["email"] if g["use_email"] and g["email_to"] else [])
    return out


def message_context(rep_dict: dict, group: dict, duty: str, author: str) -> dict:
    """Контекст плейсхолдеров для шаблона раздела «Ночной отчёт»."""
    from ..domain.templates import items_block

    return {
        "date": rep_dict.get("date") or "",
        "shift": rep_dict.get("shift_label") or "",
        "service": group.get("service_name") or "",
        "items": items_block([{"area": d.get("area"), "text": d.get("text"),
                               "comment": d.get("comment")} for d in group["defects"]
                              if d.get("sendable")]),
        "duty": duty,
        "author": author,
        "time": rep_dict.get("sent_time") or "",
    }
