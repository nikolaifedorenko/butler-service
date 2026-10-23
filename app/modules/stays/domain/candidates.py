"""Подбор кандидатов и подмена (§4.5): на смене, не в отсутствии, нагрузка после
назначения не больше лимита. Порядок: знает гостя → тот же объект или корпус → меньше нагрузка."""
from __future__ import annotations

import datetime as dt
from typing import Mapping, Sequence

from .types import OFF, Candidate, DutyDay


def rank_candidates(day: dt.date, guest_ids: set[int], unit_id: int | None, building: str,
                    escorts: Sequence[int], duty: Mapping[tuple[int, dt.date], DutyDay],
                    loads: Mapping[int, float], add_weight: float, limit: float,
                    known: Mapping[int, set[int]], places: Mapping[int, set[tuple[str, object]]],
                    replacement_codes: frozenset[str]) -> list[Candidate]:
    out = []
    for e in escorts:
        d = duty.get((e, day), OFF)
        if not d.on_shift or d.code in replacement_codes:
            continue
        after = loads.get(e, 0.0) + add_weight
        if after > limit:
            continue
        here = places.get(e, set())
        out.append(Candidate(e, bool(known.get(e, set()) & guest_ids),
                             ("unit", unit_id) in here or ("building", building) in here, after,
                             "есть отлучка в смене" if d.partial_absence else ""))
    return sorted(out, key=lambda c: (not c.knows_guest, not c.same_place, c.load_after, c.employee_id))
