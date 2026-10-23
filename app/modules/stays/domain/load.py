"""Нагрузка батлеров на день (§4.3): вес объекта делится поровну между теми, кто ведёт
гостей в нём; надбавка VIP/VVIP — батлеру этого гостя, при нескольких — поровну."""
from __future__ import annotations

from typing import Sequence

from .types import DayCover, StayDay


def day_loads(stays: Sequence[StayDay], cover: DayCover, vip_bonus: float, vvip_bonus: float) -> dict[int, float]:
    loads: dict[int, float] = {}
    places: dict[object, tuple[float, set[int]]] = {}
    for s in stays:
        # одна вилла группы — один вес; без объекта — вес брони
        key = ("u", s.unit_id) if s.unit_id is not None else ("r", s.reservation_id)
        weight, who = places.setdefault(key, (s.weight, set()))
        for g, level in s.guests.items():
            emps = cover.by_guest.get((s.reservation_id, g), ())
            who.update(emps)
            bonus = vvip_bonus if level == "vvip" else vip_bonus if level == "vip" else 0.0
            for e in emps:
                loads[e] = loads.get(e, 0.0) + bonus / len(emps)
    for weight, who in places.values():
        for e in who:
            loads[e] = loads.get(e, 0.0) + weight / len(who)
    return loads
