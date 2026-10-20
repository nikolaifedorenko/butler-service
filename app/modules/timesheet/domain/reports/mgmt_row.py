"""mgmt_row(codes, day) — итоговые коды УТ дня: агрегация размещённых блоков по
placed_day и tariff (6.3, стадия 14). Только итоговое состояние (3.4)."""
from __future__ import annotations

import datetime as dt
from typing import Mapping

from ..placement.codes import Codes


def mgmt_row(codes: Codes, day: dt.date) -> Mapping[str, int]:
    row: dict[str, int] = {}
    for b in codes.blocks():
        if b.placed_day == day:
            row[b.tariff] = row.get(b.tariff, 0) + b.minutes
    return row
