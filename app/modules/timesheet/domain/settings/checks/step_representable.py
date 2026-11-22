"""CHK-STEP-REPRESENTABLE: шаг кратен 3 минутам — грануле формата значения Табеля (3.3).

Значение Табеля — сотые доли часа (0,01 ч = 0,6 мин): представимы только длительности,
кратные 3 минутам. Каждая расчётная длительность кратна шагу, поэтому шаг, не кратный 3
(10, 20, 5, …), допускает длительности, непредставимые в ключе CFG-WINDOWS
(fmt_hours отказывает; CHK-PLAN-FORMAT и строгие дисплейные пути — частные следствия).
"""
from __future__ import annotations

from ..types import Settings
from ._violations import Violation

CHK_STEP_REPRESENTABLE = "CHK-STEP-REPRESENTABLE"


def check_step_representable(st: Settings) -> list[Violation]:
    step = st.step_minutes
    ok = isinstance(step, int) and step > 0 and step % 3 == 0
    return [] if ok else [(CHK_STEP_REPRESENTABLE, {"step_minutes": step})]
