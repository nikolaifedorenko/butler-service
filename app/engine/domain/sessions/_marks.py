"""Доступ к типу и моменту отметки: ядро работает и с Mark, и с CalcMark (4.3, 4.5)."""
from __future__ import annotations

import datetime as dt

from ..types.entities import KIND_IN, CalcMark, Mark


def kind_of(mark: Mark | CalcMark) -> str:
    return mark.source.kind if isinstance(mark, CalcMark) else mark.kind


def moment_of(mark: Mark | CalcMark) -> dt.datetime:
    return mark.at_calc if isinstance(mark, CalcMark) else mark.at_utc


def is_in(mark: Mark | CalcMark) -> bool:
    return kind_of(mark) == KIND_IN
