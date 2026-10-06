"""Общий шаг всех сценариев: settle() → evaluate_flags() → склейка."""
from __future__ import annotations

import datetime as dt

from ..domain.flags.evaluate_flags import evaluate_flags
from ..domain.pipeline.settle import settle
from .load_inputs import Inputs
from .period_view import PeriodView


def compute(inp: Inputs, now: dt.datetime, mode: str, closed: bool = False) -> PeriodView:
    result = settle(inp.period, inp.days, inp.marks, inp.opening_mark, inp.bank_open, inp.adjustments,
                    inp.deferred_in, inp.st, now, mode, inp.previous_step)
    flags = evaluate_flags(inp.period, inp.days, result.cards, inp.marks, inp.opening_mark, inp.shifts,
                           inp.absences, inp.st, now)
    return PeriodView(result, flags, inp.st.versions, closed)
