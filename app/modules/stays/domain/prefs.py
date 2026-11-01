"""Пожелания гостя к объекту (часть 2, §5): чистый счёт без БД.

Пожелание — (вид, ref_id, priority): узел фонда (объект в его ветке), флаг (у объекта есть флаг в
версии фонда дня) или объект (тот же постоянный id либо его наследник по lineage). Счёт объекта —
сумма priority выполненных пожеланий, больше — лучше."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Collection, Mapping

KINDS = ("group", "flag", "unit")


@dataclass(frozen=True)
class Pref:
    kind: str          # group | flag | unit
    ref_id: int
    priority: int


def successors(edges: Collection[tuple[int, int]]) -> Mapping[int, frozenset[int]]:
    """Наследники объектов по lineage: edges — пары (предшественник, объект); результат —
    предшественник → все объекты, получившиеся из него (транзитивно, без него самого)."""
    direct: dict[int, set[int]] = {}
    for pred, uid in edges:
        direct.setdefault(pred, set()).add(uid)
    out: dict[int, frozenset[int]] = {}
    for root in direct:
        seen: set[int] = set()
        todo = [root]
        while todo:
            for nxt in direct.get(todo.pop(), ()):
                if nxt not in seen and nxt != root:
                    seen.add(nxt)
                    todo.append(nxt)
        out[root] = frozenset(seen)
    return out


def satisfied(pref: Pref, unit_id: int, group_path: tuple[int, ...], flags: Collection[int],
              heirs: Mapping[int, frozenset[int]]) -> bool:
    if pref.kind == "group":
        return pref.ref_id in group_path
    if pref.kind == "flag":
        return pref.ref_id in flags
    return unit_id == pref.ref_id or unit_id in heirs.get(pref.ref_id, ())


def scorer(prefs: list[Pref], heirs: Mapping[int, frozenset[int]]) -> Callable[..., int]:
    """score(unit_id, group_path, flags) → сумма priority выполненных пожеланий."""
    def score(unit_id: int, group_path: tuple[int, ...], flags: Collection[int]) -> int:
        return sum(p.priority for p in prefs if satisfied(p, unit_id, group_path, flags, heirs))
    return score
