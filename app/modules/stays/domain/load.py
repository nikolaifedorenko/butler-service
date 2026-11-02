"""Нагрузка батлеров на день (§4.2): место — объект (бронь без объекта — своё место); вес места
с коэффициентами кода и «Особого гостя» делится поровну между теми, кто ведёт гостей в нём.
Отдельных надбавок батлеру гостя нет."""
from __future__ import annotations

from typing import Sequence

from .escort import place_weight
from .types import DayCover, StayDay


def day_loads(stays: Sequence[StayDay], cover: DayCover, special_factor: float) -> dict[int, float]:
    places: dict[object, tuple[float, list[float], list[bool], set[int]]] = {}
    for s in stays:
        # одна вилла группы — один вес; без объекта — своё место
        key = ("u", s.unit_id) if s.unit_id is not None else ("r", s.reservation_id)
        _weight, factors, special, who = places.setdefault(key, (s.weight, [], [], set()))
        if s.code_factor is not None:
            factors.append(s.code_factor)
        special.append(any(s.guests.values()))
        for g in s.guests:
            who.update(cover.by_guest.get((s.reservation_id, g), ()))
    loads: dict[int, float] = {}
    for weight, factors, special, who in places.values():
        w = place_weight(weight, factors, any(special), special_factor)
        for e in who:
            loads[e] = loads.get(e, 0.0) + w / len(who)
    return loads
