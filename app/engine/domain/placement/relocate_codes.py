import datetime as dt
from typing import Mapping, Sequence

from ..codes_registry.reason_codes import PASS_PRIMARY
from ..settings.types import Settings
from ..types.entities import Day
from ..types.results import DayCard, Reason
from .codes import Codes
from .merge_same_blocks import merge_same_blocks
from .pending_blocks import pending_blocks
from .place_block import place_block
from .placement_order import placement_order


def relocate_codes(cards: Sequence[DayCard], days: Mapping[dt.date, Day], codes: Codes,
                   st: Settings, pass_: str = PASS_PRIMARY) -> tuple[Reason, ...]:
    """Стадия 8: разместить все неразмещённые блоки по Т9."""
    ordered = placement_order(merge_same_blocks(pending_blocks(codes)), st)
    return tuple(r for b in ordered for r in place_block(b, cards, days, codes, st, pass_))
