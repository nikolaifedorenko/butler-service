"""Предупреждения дня (§4.4): не хранятся — считаются при каждом чтении против Графика.
Код дня из replacement_codes (отпуск, больничный) — «нужна подмена», а не «вне смены»."""
from __future__ import annotations

import datetime as dt
from typing import Mapping, Sequence

from .types import OFF, DayCover, DutyDay, Line, StayDay, Warning


def day_warnings(day: dt.date, stays: Sequence[StayDay], lines: Sequence[Line], cover: DayCover,
                 loads: Mapping[int, float], duty: Mapping[tuple[int, dt.date], DutyDay], limit: float,
                 replacement_codes: frozenset[str]) -> list[Warning]:
    out: list[Warning] = []
    by_res = {s.reservation_id: s for s in stays}
    for rid, guests in cover.uncovered.items():
        s = by_res[rid]
        if s.escorted and not s.declined:
            out.append(Warning("hole", day, None, rid, s.unit_id, ",".join(map(str, guests))))
    for rid, g, _emps in cover.double:
        out.append(Warning("double_cover", day, None, rid, by_res[rid].unit_id, str(g)))
    serving: dict[int, set[int]] = {}
    for (rid, _g), emps in cover.by_guest.items():
        for e in emps:
            serving.setdefault(e, set()).add(rid)
    for e in sorted({ln.employee_id for ln in lines} | set(serving)):
        d = duty.get((e, day), OFF)
        if d.code in replacement_codes:
            out += [Warning("need_replacement", day, e, rid, by_res[rid].unit_id, d.code)
                    for rid in sorted(serving.get(e, ()))]
        elif not d.on_shift:
            out.append(Warning("off_shift", day, e, None, None, d.code or ""))
        if loads.get(e, 0.0) > limit:
            out.append(Warning("overload", day, e, None, None, f"{loads[e]:g}/{limit:g}"))
    return out
