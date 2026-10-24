"""Кто кого ведёт в день (§4.2): явный список гостей сильнее «вся бронь/группа»; шаблоны
покрытия заполняют только пустые дни. Переезд действий не требует: объект — у гостя."""
from __future__ import annotations

import datetime as dt
from typing import Literal, Mapping, Sequence

from .types import OFF, DayCover, DutyDay, Line, StayDay


def _targets(line: Line, s: StayDay) -> bool:
    return line.reservation_id == s.reservation_id or (line.group_id is not None and line.group_id == s.group_id)


def resolve_day(stays: Sequence[StayDay], lines: Sequence[Line]) -> DayCover:
    by_guest: dict[tuple[int, int], tuple[int, ...]] = {}
    uncovered: dict[int, tuple[int, ...]] = {}
    double = []
    for s in stays:
        mine = [ln for ln in lines if _targets(ln, s)]
        whole = tuple(sorted({ln.employee_id for ln in mine if not ln.guest_ids}))
        free = []
        for g in sorted(s.guests):
            explicit = tuple(sorted({ln.employee_id for ln in mine if g in ln.guest_ids}))
            who = explicit or whole
            if len(who) > 1:                     # два явных или два «целиком» (бронь и группа)
                double.append((s.reservation_id, g, who))
            if who:
                by_guest[(s.reservation_id, g)] = who
            else:
                free.append(g)
        if free:
            uncovered[s.reservation_id] = tuple(free)
    return DayCover(by_guest, uncovered, double)


def fill_template(kind: Literal["pair", "single"], days: Sequence[dt.date], butlers: tuple[int, ...],
                  duty: Mapping[tuple[int, dt.date], DutyDay], busy_days: set[dt.date]) -> list[tuple[dt.date, int]]:
    """«Пара посменно» (A, B): ведёт тот, кто на смене, оба — A, никого — день пустой.
    «Один на весь срок» (X): X каждый день, «вне смены» покажут предупреждения."""
    out = []
    for d in days:
        if d in busy_days:
            continue
        if kind == "single":
            out.append((d, butlers[0]))
            continue
        on = [b for b in butlers if duty.get((b, d), OFF).on_shift]
        if on:
            out.append((d, on[0]))
    return out
