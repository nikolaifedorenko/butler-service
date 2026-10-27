"""Автораспределение сегментов броней по объектам (PoC SPEC §6.3, спецификация §4.1).

Детерминированный «первый подходящий»: закрепления уважаются, блоки и OOO занимают
объект, длинные брони раньше коротких при равном старте. Дополнения шахматки: группа
совместного проживания приходит одним элементом, при переезде предпочитается другой
объект того же узла дерева фонда, иначе ближайшего по дереву. Чистая функция: данные готовые, БД не видит.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from .candidates import common_prefix
from .halfday import Segment, overlaps

Key = tuple[str, int]                  # ("r", reservation_id) | ("g", group_id)


@dataclass(frozen=True)
class UnitRef:
    id: int
    category_id: int
    group_path: tuple[int, ...]        # узел дерева фонда от корня; () — без узла
    cat_sort: int
    label: str


@dataclass(frozen=True)
class HoldRef:
    unit_id: int
    start_pos: int
    end_pos: int
    title: str


@dataclass(frozen=True)
class AllocItem:
    key: Key
    number: str
    segments: tuple[Segment, ...]
    pinned: Mapping[int, int] = field(default_factory=dict)     # seg_index → unit_id


@dataclass(frozen=True)
class AllocWarning:
    kind: str                          # unassigned | pin_invalid | pin_conflict
    key: Key
    seg_index: int
    text: str


def natural_key(s: str) -> tuple:
    """«402» < «4003» < «4010»; «B-2» < «B-10»; чисто числовые — раньше буквенных."""
    return tuple((0, int(t), "") if t.isdigit() else (1, 0, t.lower())
                 for t in re.split(r"(\d+)", s) if t)


def _nearness(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    """Тот же узел (и оба без узла) — ближе всего; иначе длина общего префикса пути."""
    return len(a) + 1 if a == b else common_prefix(a, b)


def allocate(units: Sequence[UnitRef], holds: Sequence[HoldRef], items: Sequence[AllocItem],
             category_codes: Mapping[int, str]) -> tuple[dict[tuple[Key, int], int | None],
                                                         list[AllocWarning]]:
    ordered = sorted(units, key=lambda u: (u.cat_sort, natural_key(u.label), u.id))
    by_id = {u.id: u for u in ordered}
    by_cat: dict[int, list[UnitRef]] = {}
    for u in ordered:
        by_cat.setdefault(u.category_id, []).append(u)
    busy: dict[int, list[tuple[int, int, str]]] = {u.id: [] for u in ordered}
    for h in holds:
        if h.unit_id in busy:
            busy[h.unit_id].append((h.start_pos, h.end_pos, h.title))

    result: dict[tuple[Key, int], int | None] = {}
    warnings: list[AllocWarning] = []
    todo: list[tuple[AllocItem, Segment]] = []
    for it in sorted(items, key=lambda i: (natural_key(i.number), i.key)):
        for s in it.segments:
            uid = it.pinned.get(s.index)
            unit = by_id.get(uid) if uid is not None else None
            if uid is None:
                todo.append((it, s))
            elif unit is None or unit.category_id != s.category_id:
                warnings.append(AllocWarning(
                    "pin_invalid", it.key, s.index,
                    f"Бронь {it.number}: закреплённый объект не подходит — сегмент {s.index + 1} "
                    "распределяется автоматически"))
                todo.append((it, s))
            else:
                for bs, be, desc in busy[unit.id]:
                    if overlaps(s.start_pos, s.end_pos, bs, be):
                        warnings.append(AllocWarning(
                            "pin_conflict", it.key, s.index,
                            f"Бронь {it.number}: закреплённый объект {unit.label} конфликтует с «{desc}»"))
                busy[unit.id].append((s.start_pos, s.end_pos, f"бронь {it.number}"))
                result[(it.key, s.index)] = unit.id

    todo.sort(key=lambda t: (t[1].start_pos, -(t[1].end_pos - t[1].start_pos),
                             natural_key(t[0].number), t[0].key, t[1].index))
    for it, s in todo:
        cands = [u for u in by_cat.get(s.category_id, [])
                 if not any(overlaps(s.start_pos, s.end_pos, bs, be) for bs, be, _ in busy[u.id])]
        prev = result.get((it.key, s.index - 1))
        if prev is not None and len(cands) > 1:
            # переезд: другой объект, по возможности в том же узле, иначе ближе по дереву (PoC §14.4)
            others = [u for u in cands if u.id != prev] or cands
            near = {u.id: _nearness(u.group_path, by_id[prev].group_path) for u in others}
            best = max(near.values())
            cands = [u for u in others if near[u.id] == best] if best else others
        if cands:
            unit = cands[0]
            busy[unit.id].append((s.start_pos, s.end_pos, f"бронь {it.number}"))
            result[(it.key, s.index)] = unit.id
        else:
            result[(it.key, s.index)] = None
            warnings.append(AllocWarning(
                "unassigned", it.key, s.index,
                f"Бронь {it.number}: нет свободных объектов категории "
                f"{category_codes.get(s.category_id, '?')} на "
                f"{s.start.strftime('%d.%m')}–{s.end.strftime('%d.%m')}"))
    return result, warnings
