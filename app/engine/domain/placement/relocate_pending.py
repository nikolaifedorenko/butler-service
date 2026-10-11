"""relocate_pending(cards, days, codes, st) — повторное размещение (6.3, стадия 12,
только close): тот же алгоритм для оставшихся неразмещённых, в ёмкость, освобождённую
каскадом; уже размещённые не перемещаются; второго каскада нет (pass=after_cascade)."""
from __future__ import annotations

import datetime as dt
from typing import Mapping, Sequence

from ..codes_registry.reason_codes import PASS_AFTER_CASCADE
from ..settings.types import Settings
from ..types.entities import Day
from ..types.results import DayCard, Reason
from ._relocate import relocate


def relocate_pending(cards: Sequence[DayCard], days: Mapping[dt.date, Day], codes,
                     st: Settings) -> tuple[Reason, ...]:
    return relocate(cards, days, codes, st, PASS_AFTER_CASCADE)
