"""to_calc_mark(mark, st) — расчётная отметка: округлённый момент + связь с исходной (3.2)."""
from __future__ import annotations

from ..settings.types import Settings
from ..types.entities import CalcMark, Mark
from .round_moment import round_moment


def to_calc_mark(mark: Mark, st: Settings) -> CalcMark:
    return CalcMark(source=mark, at_calc=round_moment(mark.at_utc, st))
