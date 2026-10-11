"""INV-CLOSE-BALANCE (частично) и INV-CUT-POSITIVE (10.1: после стадии 11)."""
from __future__ import annotations

from typing import Sequence

from ..codes_registry.invariant_codes import INV_CLOSE_BALANCE, INV_CUT_POSITIVE
from ..settings.types import Settings
from ..types.results import Cut
from ._fail import fail


def check_cascade(need: int, cuts: Sequence[Cut], residual: int, st: Settings) -> None:
    paid = sum(c.paid_minutes for c in cuts)
    if need != paid + residual or residual < 0:
        fail(INV_CLOSE_BALANCE, {"need": need, "paid_by_cuts": paid, "residual": residual})
    for c in cuts:
        weight = st.weights[c.tariff]
        if c.taken_minutes <= 0 or c.taken_minutes % st.step_minutes \
                or c.paid_minutes != c.taken_minutes * weight:
            fail(INV_CUT_POSITIVE, {"source_day": c.source_day, "tariff": c.tariff,
                                    "taken": c.taken_minutes, "paid": c.paid_minutes})
