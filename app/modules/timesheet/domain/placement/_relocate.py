"""Общий алгоритм размещения (стадии 8 и 12): pending → merge → порядок → place_block."""
from __future__ import annotations

import datetime as dt
from typing import Mapping, Sequence

from ..settings.types import Settings
from ..types.entities import Day
from ..types.results import DayCard, Reason
from .codes import Codes
from .merge_same_blocks import merge_same_blocks
from .pending_blocks import pending_blocks
from .place_block import place_block
from .placement_order import placement_order


def relocate(cards: Sequence[DayCard], days: Mapping[dt.date, Day], codes: Codes,
             st: Settings, pass_: str) -> tuple[Reason, ...]:
    ordered = placement_order(merge_same_blocks(pending_blocks(codes)), st)
    return tuple(r for b in ordered for r in place_block(b, cards, days, codes, st, pass_))
