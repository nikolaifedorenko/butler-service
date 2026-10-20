"""CHK-WINDOW-BOUNDS: окно не пустое, начало < конца, границы в пределах суток;
окно не пересекает полночь (CFG-WINDOWS)."""
from __future__ import annotations

from ..types import Settings
from ._violations import Violation

CHK_WINDOW_BOUNDS = "CHK-WINDOW-BOUNDS"


def check_window_bounds(st: Settings) -> list[Violation]:
    return [(CHK_WINDOW_BOUNDS, {"value": key, "start_minute": w.start_minute, "end_minute": w.end_minute})
            for key, w in st.windows.items()
            if not (0 <= w.start_minute < w.end_minute <= 1440)]
