"""CHK-GRID: все границы окон CFG-WINDOWS и категорий CFG-CATEGORIES кратны шагу
расчёта от начала суток (5.3, 4.5)."""
from __future__ import annotations

from ..types import Settings
from ._violations import Violation

CHK_GRID = "CHK-GRID"


def check_grid(st: Settings) -> list[Violation]:
    step = st.step_minutes
    if not isinstance(step, int) or step <= 0:
        return []                                   # нарушение покроет CHK-STEP-DIVIDES-60
    out: list[Violation] = [(CHK_GRID, {"kind": "window", "value": key, "minute": m})
           for key, w in st.windows.items() for m in (w.start_minute, w.end_minute) if m % step]
    out += [(CHK_GRID, {"kind": "category", "value": c.code, "minute": m})
            for c in st.categories for m in (c.start_minute, c.end_minute) if m % step]
    return out
