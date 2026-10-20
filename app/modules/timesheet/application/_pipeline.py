"""Общий шаг сценариев вкладки «Управленческий табель» (16.6): settle → извлечь
plan_equals_fact из карточек → evaluate_flags (7.1). Единственное место, где тяжёлый
конвейер вызывает application."""
from __future__ import annotations

import datetime as dt

from ..domain.flags.evaluate_flags import evaluate_flags
from ..domain.pipeline.settle import settle
from .load_inputs import Inputs
from .period_view import PeriodView


def run_pipeline(inp: Inputs, now: dt.datetime, mode: str) -> PeriodView:
    result = settle(inp.period, inp.days, inp.marks, inp.opening_mark, inp.bank_open,
                    inp.adjustments, inp.deferred_in, inp.st, now, mode, inp.previous_step)
    pef = {card.day: card.plan_equals_fact_applied for card in result.cards}
    flags = evaluate_flags(inp.period, inp.days, pef, inp.marks, inp.opening_mark,
                           inp.shifts, inp.absences, inp.st, now)
    return PeriodView(result, flags, inp.employment, inp.days)
