"""merge_absences(absences) — канонический список согласованных отсутствий: слияние
пересекающихся и примыкающих на UTC-оси (4.7, v7/R17; отсутствие может пересекать полночь)."""
from __future__ import annotations

from typing import Sequence

from ..types.entities import Absence
from .shift_segments import Segment, merge_spans


def merge_absences(absences: Sequence[Absence]) -> tuple[Segment, ...]:
    return merge_spans([(a.start_utc, a.end_utc) for a in absences])
