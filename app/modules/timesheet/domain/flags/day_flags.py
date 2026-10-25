"""day_flags — композиция флагов дня (6.6, стадия 5–6; сигнатура зафиксирована в v7.1):
late + early + off_shift, подавление LATE(None), канонический порядок (3.4):
порядок кодов реестра 6.6, затем возрастание временного ключа."""
from __future__ import annotations

import datetime as dt
from typing import Sequence, cast

from ..codes_registry.flag_codes import ALL as FLAG_ORDER
from ..schedule.shift_segments import Segment
from ..settings.types import Settings
from ..types.entities import Day, RawInterval
from ..types.results import Flag
from .drop_suppressed_lates import drop_suppressed_lates
from .early import early_flag
from .late import late_flag
from .off_shift import off_shift_flag


def _time_key(flag: Flag) -> dt.datetime:
    # у флагов дня всегда есть один из моментов (6.6); data — Mapping[str, object]
    return cast(dt.datetime, flag.data.get("expected_at") or flag.data.get("first_presence_at"))


def day_flags(day: Day, subintervals: Sequence[Segment], raw_intervals: Sequence[RawInterval],
              segments: Sequence[Segment], absences: Sequence[Segment],
              plan_equals_fact_applied: bool, now: dt.datetime, st: Settings) -> tuple[Flag, ...]:
    lates = drop_suppressed_lates(late_flag(subintervals, raw_intervals, now, st),
                                  plan_equals_fact_applied)
    early = early_flag(subintervals, raw_intervals, now, st)
    off = off_shift_flag(subintervals, raw_intervals, segments, absences, day)
    collected = [*lates, *early] + ([off] if off is not None else [])
    return tuple(sorted(collected, key=lambda f: (FLAG_ORDER.index(f.code), _time_key(f))))
