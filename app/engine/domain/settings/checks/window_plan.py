"""CHK-WINDOW-PLAN: информационный план, закодированный в ключе значения, ≤ длины окна
(зарплатная гигиена, RUL-PLAN-BELOW-WINDOW; v7.1: план карточки = окно и не затрагивается)."""
from __future__ import annotations

from ..types import Settings
from ._violations import Violation
from ._window_key import parse_key

CHK_WINDOW_PLAN = "CHK-WINDOW-PLAN"


def check_window_plan(st: Settings) -> list[Violation]:
    out = []
    for key, window in st.windows.items():
        parsed = parse_key(key)
        if parsed is not None and parsed[1] > window.length:
            out.append((CHK_WINDOW_PLAN, {"value": key, "plan_minutes": parsed[1],
                                          "window_length": window.length}))
    return out
