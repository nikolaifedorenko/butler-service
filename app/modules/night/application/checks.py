"""Сверки справочника ночного обхода для экрана «Настройки → Обзор»."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..adapters.orm import NightArea, NightZone, ZoneChecklistItem


def overview_checks(db: Session) -> list[dict]:
    """Зоны, у которых есть объекты, но шаблон чек-листа пуст."""
    out: list[dict] = []
    zones = {z.id: z.name for z in db.scalars(
        select(NightZone).where(NightZone.active.is_(True)))}
    if not zones:
        return out
    areas_by_zone = dict(db.execute(
        select(NightArea.zone_id, func.count(NightArea.id))
        .where(NightArea.active.is_(True), NightArea.zone_id.is_not(None))
        .group_by(NightArea.zone_id)).all())
    with_items = set(db.scalars(select(ZoneChecklistItem.zone_id)
                                .where(ZoneChecklistItem.active.is_(True)).distinct()))
    for zid, zname in sorted(zones.items(), key=lambda kv: kv[1]):
        if areas_by_zone.get(zid) and zid not in with_items:
            out.append({"code": "APP-NIGHT-ZONE-NO-TEMPLATE", "level": "warn", "screen": "night",
                        "text": (f"Зона «{zname}»: в шаблоне чек-листа нет активных пунктов — "
                                 f"объекты зоны ({areas_by_zone[zid]}) проверяются только по "
                                 f"индивидуальным пунктам. Задайте шаблон в «Настройки → Ночной обход»")})
    return out
