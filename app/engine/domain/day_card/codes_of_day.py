"""codes_of_day(day, parts, st) — коды УТ дня: категории переработки + вес дня,
имена слитно («ДЯ», «ДН», «ДЯ2», «ДН2»); длительности не округляются (4.5)."""
from __future__ import annotations

from typing import Mapping, Sequence

from ..settings.types import Settings
from ..types.entities import Day, Interval, Minutes
from .classify_overtime import classify_overtime
from .code_name import code_name
from .weight_of_day import weight_of_day


def codes_of_day(day: Day, parts: Sequence[Interval], st: Settings) -> Mapping[str, Minutes]:
    weight = weight_of_day(day, st)
    out: dict[str, Minutes] = {}
    for category, minutes in classify_overtime(parts, st).items():
        code = code_name(category, weight)
        out[code] = out.get(code, 0) + minutes
    return out
