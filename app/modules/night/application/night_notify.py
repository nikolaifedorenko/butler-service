"""Недостатки ночной смены и их отправка службам (этап 5).

Use-case'ы экрана «Недостатки смены»: собрать позиции к отправке, показать
предпросмотр, отправить вручную (всё скопом или выбранное) и отдать общий журнал.

Границы: домен (``app/night.py``) не знает про транспорт, транспорт
(``app/notify``) — про ночной отчёт; связывает их этот сервис. Ошибки —
исключения ``core.errors`` (main.py маппит их в статусы), audit и commit —
часть use-case'а (ADR-0006).

Правила отправки (решения владельца от 19.10.2026):
  * только вручную: ни закрытие объекта, ни закрытие смены ничего не отправляют;
  * отправить может любой пользователь обхода (нового права не вводили);
  * отправленное помечается и повторно не уходит;
  * если недостаток исправили ПОСЛЕ отправки — не отправляем ничего
    (ни «исправлено», ни отзыва сообщения);
  * «Не проверено» включается в отчёт отдельным блоком;
  * общая служба у нескольких получателей не объединяется: каждая служба получает
    своё сообщение со своим составом.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.errors import Conflict, Validation
from app.core.time import now_local
from app.modules.notify.application.config import load_config
from app.modules.notify.application.dispatch import attachments_of, dispatch_dict, journal_of, send_group
from app.modules.notify.application.recipients import group_by_service, message_context
from app.modules.notify.application.templates import PLACEHOLDERS, render_template, template_of

from ..adapters.orm import NightCheckItem, NightReport
from .night import defects_of, duty_of

DOMAIN = "night"


def _report_brief(rep: NightReport) -> dict:
    return {"id": rep.id, "date": rep.date.isoformat(), "shift_label": rep.shift_label,
            "status": rep.status, "readonly": rep.status == "closed"}


def defects_payload(db: Session, rep: NightReport) -> dict:
    """Данные экрана «Недостатки смены»: позиции, группы по службам, журнал, шаблон."""
    data = defects_of(db, rep)
    cfg = load_config(db)
    return {
        "report": _report_brief(rep),
        "duty": duty_of(rep),
        "counts": data["counts"],
        "items": data["items"],
        "groups": group_by_service(db, data["items"]),
        "dispatches": [dispatch_dict(d) for d in journal_of(db, DOMAIN, rep.id, limit=50)],
        "template": {"text": template_of(db, DOMAIN), "placeholders": PLACEHOLDERS.get(DOMAIN, [])},
        "transport": {"telegram": cfg.telegram_ready, "email": cfg.email_ready},
    }


def preview_message(db: Session, rep: NightReport, group: dict,
                    author: str = "") -> str:
    """Текст сообщения службе — тот же рендер, что при отправке (предпросмотр)."""
    ctx = message_context(_report_brief(rep) | {"sent_time": f"{now_local():%H:%M}"},
                          group, duty_of(rep), author or "—")
    return render_template(template_of(db, DOMAIN), ctx)


def dispatch_defects(db: Session, rep: NightReport, principal: Principal, *,
                     mode: str = "all", item_ids: Optional[list[int]] = None,
                     service_ids: Optional[list[int]] = None,
                     bot=None, mailer=None) -> dict:
    """Отправить недостатки службам вручную: всё скопом (mode="all") или выбранное.

    Возвращает {"sent", "failed", "marked", "dispatches", "skipped"}: skipped —
    группы, которым отправить нельзя (нет канала/получателя, служба отключена),
    с причинами — их показывает интерфейс, а не прячет в ошибку.
    """
    cfg = load_config(db)
    if not cfg.telegram_ready and not cfg.email_ready:
        raise Conflict("Доставка не настроена: заполните токен бота или почту "
                       "в «Настройки → Чаты и Почта»")

    if mode not in ("all", "selected"):
        raise Validation("Режим отправки: all или selected")

    data = defects_of(db, rep)
    rows = [d for d in data["items"] if d["sendable"]]
    if mode == "selected":
        wanted = {int(i) for i in (item_ids or [])}
        rows = [d for d in rows if d["id"] in wanted]
    if service_ids:
        allowed = {int(i) for i in service_ids}
        rows = [d for d in rows if d.get("service_id") in allowed]
    if not rows:
        raise Validation("Не выбрано ни одного недостатка для отправки "
                         "(возможно, всё уже отправлено или исправлено после отправки)")

    groups = group_by_service(db, rows)
    author = principal.actor_label
    ts = now_local()
    sent = failed = marked = 0
    dispatches: list[dict] = []
    skipped: list[dict] = []

    for group in groups:
        sendable = [d for d in group["defects"] if d["sendable"]]
        if not sendable:
            continue
        if group["problems"] or not group["channels"]:
            skipped.append({"service_id": group["service_id"],
                            "service_name": group["service_name"],
                            "defects": len(sendable),
                            "problems": group["problems"] or ["канал доставки не заполнен"]})
            continue
        message = preview_message(db, rep, group, author)
        subject = f"Ночной отчёт {rep.date:%d.%m.%Y} · {group['service_name']}"
        media_ids = [p["id"] for d in sendable for p in (d.get("media") or [])]
        attachments = attachments_of(db, media_ids)
        rows_journal = send_group(db, domain=DOMAIN, ref_id=rep.id,
                                  actor_id=principal.user.id, actor_name=author,
                                  group=group, message=message, subject=subject,
                                  attachments=attachments, cfg=cfg, bot=bot, mailer=mailer)
        ok = [r for r in rows_journal if r.status == "sent"]
        for r in rows_journal:
            dispatches.append(dispatch_dict(r))
            if r.status == "sent":
                sent += 1
            else:
                failed += 1
        if ok:
            # отправленное помечаем: повторно эти позиции не уйдут
            first_id = ok[0].id
            ids = [d["id"] for d in sendable]
            for ni in db.scalars(select(NightCheckItem).where(NightCheckItem.id.in_(ids))):
                ni.dispatch_id = first_id
                ni.dispatched_at = ts
            marked += len(ids)
    db.flush()
    audit(db, principal, "night_dispatch", f"report:{rep.id}",
          {"mode": mode, "sent": sent, "failed": failed, "marked": marked,
           "skipped": [s["service_name"] for s in skipped]})
    db.commit()
    return {"ok": True, "sent": sent, "failed": failed, "marked": marked,
            "dispatches": dispatches, "skipped": skipped}


def report_journal(db: Session, rep: NightReport, limit: int = 50) -> list[dict]:
    """Журнал отправок смены (обёртка над общим журналом раздела)."""
    return [dispatch_dict(d) for d in journal_of(db, DOMAIN, rep.id, limit=limit)]
