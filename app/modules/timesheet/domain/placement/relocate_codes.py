"""relocate_codes(cards, days, codes, st) — композиция первичного размещения
(6.3, стадия 8): pending → merge → порядок CFG-PLACEMENT → place_block(pass=primary)."""
from __future__ import annotations

import datetime as dt
from typing import Mapping, Sequence

from ..codes_registry.reason_codes import PASS_PRIMARY
from ..settings.types import Settings
from ..types.entities import Day
from ..types.results import DayCard, Reason
from ._relocate import relocate


def relocate_codes(cards: Sequence[DayCard], days: Mapping[dt.date, Day], codes,
                   st: Settings) -> tuple[Reason, ...]:
    return relocate(cards, days, codes, st, PASS_PRIMARY)
