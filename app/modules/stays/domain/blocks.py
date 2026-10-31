"""Слоты блоков (спецификация OOO и блоков §4.1): блок — сетка «категория × ночь → остаток»;
слот k категории X существует в ночи, где остаток ≥ k. Непрерывные ночи слота — один `SlotRef`;
ночь D — от вечера D до утра D+1. По объектам слоты раскладывает `allocate` по ночам, поэтому
границы версий фонда (они всегда начинаются вечером) режут слот сами собой."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Mapping

from .halfday import AM, PM, pos


@dataclass(frozen=True)
class SlotRef:
    block_id: int
    category_id: int
    slot: int                          # номер слота с 1
    start_pos: int                     # pos(первая ночь, PM)
    end_pos: int                       # pos(последняя ночь + 1, AM)
    title: str


def slots(nights: Mapping[tuple[int, int, dt.date], int],
          titles: Mapping[int, str] | None = None) -> list[SlotRef]:
    """(блок, категория, ночь) → остаток ⇒ слоты по порядку (блок, категория, слот, начало)."""
    grid: dict[tuple[int, int], dict[dt.date, int]] = {}
    for (block_id, category_id, night), qty in nights.items():
        grid.setdefault((block_id, category_id), {})[night] = qty
    out: list[SlotRef] = []
    for (block_id, category_id), by_night in sorted(grid.items()):
        days = sorted(by_night)
        title = (titles or {}).get(block_id, "")
        for k in range(1, max(by_night.values(), default=0) + 1):
            run: list[dt.date] = []
            for d in [*days, None]:
                if d is not None and by_night[d] >= k and (not run or d == run[-1] + dt.timedelta(days=1)):
                    run.append(d)
                    continue
                if run:
                    out.append(SlotRef(block_id, category_id, k, pos(run[0], PM),
                                       pos(run[-1] + dt.timedelta(days=1), AM), title))
                run = [d] if d is not None and by_night[d] >= k else []
    return out
