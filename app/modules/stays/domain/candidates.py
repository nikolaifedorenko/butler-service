"""Подбор кандидатов и подмена (§4.5): на смене, не в отсутствии, нагрузка после
назначения не больше лимита. Порядок: знает гостя → тот же объект → тот же узел дерева фонда,
иначе ближе по дереву (длиннее общий префикс пути) → меньше нагрузка."""
from __future__ import annotations

import datetime as dt
from typing import Mapping, Sequence

from .types import OFF, Candidate, DutyDay


def common_prefix(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    n = 0
    for x, y in zip(a, b, strict=False):
        if x != y:
            break
        n += 1
    return n


def _closeness(here: set[tuple[str, object]], unit_id: int | None,
               group_path: tuple[int, ...]) -> tuple[bool, bool, int]:
    """(тот же объект, тот же узел, длина общего префикса пути) по местам батлера в этот день."""
    paths = [p for kind, p in here if kind == "path"]
    same_node = bool(group_path) and any(p and p[-1] == group_path[-1] for p in paths)
    return (("unit", unit_id) in here, same_node, max((common_prefix(p, group_path) for p in paths), default=0))


def rank_candidates(day: dt.date, guest_ids: set[int], unit_id: int | None, group_path: tuple[int, ...],
                    escorts: Sequence[int], duty: Mapping[tuple[int, dt.date], DutyDay],
                    loads: Mapping[int, float], add_weight: float, limit: float,
                    known: Mapping[int, set[int]], places: Mapping[int, set[tuple[str, object]]],
                    replacement_codes: frozenset[str]) -> list[Candidate]:
    """places: батлер → {("unit", id), ("path", путь узла)} — где он ведёт гостей в этот день."""
    out = []
    near: dict[int, tuple[bool, bool, int]] = {}
    for e in escorts:
        d = duty.get((e, day), OFF)
        if not d.on_shift or d.code in replacement_codes:
            continue
        after = loads.get(e, 0.0) + add_weight
        if after > limit:
            continue
        near[e] = _closeness(places.get(e, set()), unit_id, group_path)
        out.append(Candidate(e, bool(known.get(e, set()) & guest_ids), near[e][0] or near[e][1], after,
                             "есть отлучка в смене" if d.partial_absence else ""))
    return sorted(out, key=lambda c: (not c.knows_guest, not near[c.employee_id][0], not near[c.employee_id][1],
                                      -near[c.employee_id][2], c.load_after, c.employee_id))
