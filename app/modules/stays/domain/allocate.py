"""Автораспределение сегментов броней по объектам (PoC SPEC §6.3, спецификация §4.1).

Детерминированный «первый подходящий»: закрепления уважаются, блоки и OOO занимают
объект, длинные брони раньше коротких при равном старте. Дополнения шахматки: группа
совместного проживания приходит одним элементом, при переезде предпочитается другой
объект того же узла дерева фонда, иначе ближайшего по дереву. Чистая функция: данные готовые, БД не видит.

Границы версий фонда (спецификация версий §5): объект задан интервалами `UnitSpan` (категория,
узел, обозначение на отрезке половинок), сегменты брони приходят частями `Piece`, разрезанными
на границах. Объект подходит части, если его интервал нужной категории покрывает её целиком;
следующая часть того же сегмента остаётся в том же объекте, если он подходит.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from .candidates import common_prefix
from .halfday import PIECE_BASE, Piece, overlaps

Key = tuple[str, int]                  # ("r", reservation_id) | ("g", group_id)


@dataclass(frozen=True)
class UnitSpan:
    unit_id: int
    category_id: int
    cat_sort: int
    label: str
    group_path: tuple[int, ...]        # узел дерева фонда от корня; () — без узла
    start_pos: int
    end_pos: int


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
    segments: tuple[Piece, ...]                                  # части по порядку
    pinned: Mapping[int, int] = field(default_factory=dict)     # seg_index → unit_id
    # замороженные части (прошлое, заселённые): Piece.index → объект или None — не распределяются,
    # но занимают объект и служат «предыдущей частью» для продолжения сегмента
    fixed: Mapping[int, int | None] = field(default_factory=dict)


@dataclass(frozen=True)
class AllocWarning:
    kind: str                          # unassigned | pin_invalid | pin_conflict | category_missing | hold_absent
    key: Key
    piece_index: int
    text: str


def natural_key(s: str) -> tuple:
    """«402» < «4003» < «4010»; «B-2» < «B-10»; чисто числовые — раньше буквенных."""
    return tuple((0, int(t), "") if t.isdigit() else (1, 0, t.lower())
                 for t in re.split(r"(\d+)", s) if t)


def _nearness(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    """Тот же узел (и оба без узла) — ближе всего; иначе длина общего префикса пути."""
    return len(a) + 1 if a == b else common_prefix(a, b)


def _since(p: Piece) -> str:
    return f" с {p.start.strftime('%d.%m')}" if p.index % PIECE_BASE else ""


def allocate(spans: Sequence[UnitSpan], holds: Sequence[HoldRef], items: Sequence[AllocItem],
             category_codes: Mapping[int, str]) -> tuple[dict[tuple[Key, int], int | None],
                                                         list[AllocWarning]]:
    """Результат и предупреждения — по индексу части (`Piece.index`)."""
    ordered = sorted(spans, key=lambda u: (u.cat_sort, natural_key(u.label), u.unit_id, u.start_pos))
    by_cat: dict[int, list[UnitSpan]] = {}
    for u in ordered:
        by_cat.setdefault(u.category_id, []).append(u)
    busy: dict[int, list[tuple[int, int, str]]] = {u.unit_id: [] for u in ordered}
    for h in holds:
        if h.unit_id in busy:
            busy[h.unit_id].append((h.start_pos, h.end_pos, h.title))

    def fitting(p: Piece) -> list[UnitSpan]:
        """Интервалы категории части, покрывающие её целиком — по одному на объект."""
        return [u for u in by_cat.get(p.category_id, []) if u.start_pos <= p.start_pos and p.end_pos <= u.end_pos]

    result: dict[tuple[Key, int], int | None] = {}
    paths: dict[tuple[Key, int], tuple[int, ...]] = {}      # путь узла объекта на этой части
    warnings: list[AllocWarning] = []
    prev_of: dict[tuple[Key, int], Piece] = {}
    todo: list[tuple[AllocItem, Piece]] = []

    def place(it: AllocItem, p: Piece, u: UnitSpan) -> None:
        busy[u.unit_id].append((p.start_pos, p.end_pos, f"бронь {it.number}"))
        result[(it.key, p.index)] = u.unit_id
        paths[(it.key, p.index)] = u.group_path

    by_number = sorted(items, key=lambda i: (natural_key(i.number), i.key))
    for it in by_number:
        # замороженные части — раньше закреплений: закрепление поверх них даёт pin_conflict
        for p in it.segments:
            if p.index in it.fixed:
                if (uid := it.fixed[p.index]) is not None:
                    busy.setdefault(uid, []).append((p.start_pos, p.end_pos, f"бронь {it.number}"))
                    paths[(it.key, p.index)] = next((u.group_path for u in ordered if u.unit_id == uid
                                                     and u.start_pos <= p.start_pos <= u.end_pos), ())
                result[(it.key, p.index)] = uid
    for it in by_number:
        for prev, p in zip((None, *it.segments), it.segments, strict=False):
            if prev is not None:
                prev_of[(it.key, p.index)] = prev
            if p.index in it.fixed:
                continue
            uid = it.pinned.get(p.seg_index)
            if uid is None:
                todo.append((it, p))
                continue
            unit = next((u for u in fitting(p) if u.unit_id == uid), None)
            if unit is None:
                warnings.append(AllocWarning(
                    "pin_invalid", it.key, p.index,
                    f"Бронь {it.number}: закреплённый объект не подходит{_since(p)} — "
                    f"сегмент {p.seg_index + 1} распределяется автоматически"))
                todo.append((it, p))
                continue
            for bs, be, desc in busy[unit.unit_id]:
                if overlaps(p.start_pos, p.end_pos, bs, be):
                    warnings.append(AllocWarning(
                        "pin_conflict", it.key, p.index,
                        f"Бронь {it.number}: закреплённый объект {unit.label} конфликтует с «{desc}»"))
            place(it, p, unit)

    def free(u: UnitSpan, p: Piece) -> bool:
        return not any(overlaps(p.start_pos, p.end_pos, bs, be) for bs, be, _ in busy[u.unit_id])

    def keep_unit(it: AllocItem, p: Piece) -> UnitSpan | None:
        """Часть того же сегмента за границей: объект предыдущей части, если он подходит и свободен."""
        prev = prev_of.get((it.key, p.index))
        if prev is None or prev.seg_index != p.seg_index:
            return None
        uid = result.get((it.key, prev.index))
        return next((u for u in fitting(p) if u.unit_id == uid and free(u, p)), None)

    def assign(it: AllocItem, p: Piece) -> None:
        fit = fitting(p)
        if not any(overlaps(u.start_pos, u.end_pos, p.start_pos, p.end_pos) for u in by_cat.get(p.category_id, [])):
            result[(it.key, p.index)] = None
            warnings.append(AllocWarning(
                "category_missing", it.key, p.index,
                f"Бронь {it.number}: категории {category_codes.get(p.category_id, '?')} нет в фонде "
                f"с {p.start.strftime('%d.%m')}"))
            return
        cands = [u for u in fit if free(u, p)]
        prev = prev_of.get((it.key, p.index))
        prev_uid = result.get((it.key, prev.index)) if prev is not None else None
        if prev_uid is not None and prev.seg_index != p.seg_index and len(cands) > 1:
            # переезд: другой объект, по возможности в том же узле, иначе ближе по дереву (PoC §14.4)
            others = [u for u in cands if u.unit_id != prev_uid] or cands
            prev_path = paths[(it.key, prev.index)]
            near = {u.unit_id: _nearness(u.group_path, prev_path) for u in others}
            best = max(near.values())
            cands = [u for u in others if near[u.unit_id] == best] if best else others
        if cands:
            place(it, p, cands[0])
        else:
            result[(it.key, p.index)] = None
            warnings.append(AllocWarning(
                "unassigned", it.key, p.index,
                f"Бронь {it.number}: нет свободных объектов категории "
                f"{category_codes.get(p.category_id, '?')} на "
                f"{p.start.strftime('%d.%m')}–{p.end.strftime('%d.%m')}"))

    todo.sort(key=lambda t: (t[1].start_pos, -(t[1].end_pos - t[1].start_pos),
                             natural_key(t[0].number), t[0].key, t[1].index))
    groups: dict[int, list[tuple[AllocItem, Piece]]] = {}
    for t in todo:
        groups.setdefault(t[1].start_pos, []).append(t)
    for group in groups.values():
        rest = []
        # с одной половинки сначала части, остающиеся в объекте предыдущей части: иначе
        # часть, чей объект сменил категорию на границе, заняла бы чужой продолжающийся объект
        for it, p in group:
            if (unit := keep_unit(it, p)) is not None:
                place(it, p, unit)
            else:
                rest.append((it, p))
        for it, p in rest:
            assign(it, p)
    return result, warnings
