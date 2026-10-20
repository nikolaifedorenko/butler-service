"""INV-SEGMENT-WITHIN-DAY (10.1: в evaluate_flags после shift_segments): каждый отрезок
Графика, участвующий во флагах, лежит внутри одного дня."""
from __future__ import annotations

import datetime as dt
from typing import Mapping, Sequence

from ..codes_registry.invariant_codes import INV_SEGMENT_WITHIN_DAY
from ..schedule.shift_segments import Segment
from ..settings.types import Settings
from ..time.local_midnight import local_midnight, next_midnight
from ._fail import fail


def check_segments(segments: Mapping[dt.date, Sequence[Segment]], st: Settings) -> None:
    for day, items in segments.items():
        lo, hi = local_midnight(day, st.tz), next_midnight(day, st.tz)
        for start, end in items:
            if not (lo <= start < end <= hi):
                fail(INV_SEGMENT_WITHIN_DAY,
                     {"day": day, "start": start.isoformat(), "end": end.isoformat()})
