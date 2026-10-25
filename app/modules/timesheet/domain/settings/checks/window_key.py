"""CHK-WINDOW-KEY: ключ строки CFG-WINDOWS каноничен (3.3) — «<код> <часы>» через один
пробел; код существует в CFG-DAY-CODES с carries_hours = Да; часы — дробь через запятую,
≤ 2 знаков, без хвостовых нулей; минуты = часы × 60 точно."""
from __future__ import annotations

from ..types import Settings
from ._violations import Violation
from ._window_key import parse_key

CHK_WINDOW_KEY = "CHK-WINDOW-KEY"


def check_window_key(st: Settings) -> list[Violation]:
    out: list[Violation] = []
    for key in st.windows:
        parsed = parse_key(key)
        if parsed is None:
            out.append((CHK_WINDOW_KEY, {"value": key, "reason": "non_canonical_format"}))
        elif parsed[0] not in st.day_code_policy:
            out.append((CHK_WINDOW_KEY, {"value": key, "reason": "unknown_day_code"}))
        elif not st.day_code_policy[parsed[0]].carries_hours:
            out.append((CHK_WINDOW_KEY, {"value": key, "reason": "code_carries_no_hours"}))
    return out
