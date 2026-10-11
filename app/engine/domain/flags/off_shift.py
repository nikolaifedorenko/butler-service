"""off_shift_flag — OFF_SHIFT_ATTENDANCE (6.6): ожидаемых подинтервалов нет (смены нет
или она полностью покрыта отсутствием) ∧ в дне есть исходное присутствие. Смена Графика,
накрывающая день с кодом-отсутствием, флаг снимает (подинтервалы существуют).
first_presence_at — начало первого исходного интервала дня (для сессии через полночь —
синтетическая граница 00:00; синтетические границы флаги, привязанные к отметкам, не порождают)."""
from __future__ import annotations

from typing import Sequence

from ..codes_registry.flag_codes import OFF_SHIFT_ATTENDANCE
from ..schedule.shift_segments import Segment
from ..types.entities import Day, RawInterval
from ..types.results import Flag


def off_shift_flag(subintervals: Sequence[Segment], intervals: Sequence[RawInterval],
                   segments: Sequence[Segment], absences: Sequence[Segment],
                   day: Day) -> Flag | None:
    if subintervals or not intervals:
        return None
    return Flag(day.day, OFF_SHIFT_ATTENDANCE, {
        "first_presence_at": min(iv.start_utc for iv in intervals),
        "day_code": day.code,
        "shift_segments": tuple(segments),
        "absence_intervals": tuple(absences)})
