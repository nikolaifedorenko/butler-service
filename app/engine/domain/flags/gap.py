from typing import Sequence

from ..codes_registry.flag_codes import ABSENCE_GAP
from ..types.entities import Interval
from ..types.results import Flag


def gap_flags(subs: Sequence[Interval]) -> tuple[Flag, ...]:
    """ABSENCE_GAP: разрыв между соседними ожидаемыми подинтервалами (минуты дня)."""
    return tuple(Flag(a.day, ABSENCE_GAP, {"gap_start": a.end_minute, "expected_return": b.start_minute})
                 for a, b in zip(subs, subs[1:], strict=False) if b.start_minute > a.end_minute)
