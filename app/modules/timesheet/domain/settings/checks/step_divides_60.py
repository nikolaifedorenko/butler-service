"""CHK-STEP-DIVIDES-60: шаг расчёта делит 60 без остатка (5.3)."""
from __future__ import annotations

from ..types import Settings
from ._violations import Violation

CHK_STEP_DIVIDES_60 = "CHK-STEP-DIVIDES-60"


def check_step_divides_60(st: Settings) -> list[Violation]:
    step = st.step_minutes
    ok = isinstance(step, int) and step > 0 and 60 % step == 0
    return [] if ok else [(CHK_STEP_DIVIDES_60, {"step_minutes": step})]
