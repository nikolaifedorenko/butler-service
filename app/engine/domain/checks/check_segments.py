from typing import Sequence

from ..codes_registry.invariant_codes import I16
from ..types.entities import Interval
from ._fail import fail_if


def check_segments(segments: Sequence[Interval]) -> None:
    """И16: каждый отрезок Графика лежит внутри одного дня."""
    for s in segments:
        fail_if(not 0 <= s.start_minute < s.end_minute <= 1440, I16, segment=s)
