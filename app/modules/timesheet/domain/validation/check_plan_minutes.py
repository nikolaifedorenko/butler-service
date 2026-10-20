"""CHK-PLAN-CONSISTENT и CHK-PLAN-FORMAT (5.3): план согласован с кодом
(carries_hours = Нет ⇒ 0; Да ⇒ > 0) и кратен 15 — представим в нотации значения (3.3)."""
from __future__ import annotations

from typing import Sequence

from ..day_card.policy_of import policy_of
from ..settings.types import Settings
from ..types.entities import Day
from ..types.errors import InvalidInputDataError


def _violations(days: Sequence[Day], st: Settings, consistent: bool) -> tuple:
    out = []
    for day in sorted(days, key=lambda d: d.day):
        carries = policy_of(day, st).carries_hours
        bad_consistent = (day.plan_minutes != 0) if not carries else (day.plan_minutes <= 0)
        bad_format = day.plan_minutes % 15 != 0
        if (consistent and bad_consistent) or (not consistent and bad_format):
            out.append({"day": day.day, "code": day.code, "plan_minutes": day.plan_minutes})
    return tuple(out)


def check_plan_minutes(days: Sequence[Day], st: Settings) -> None:
    violations = _violations(days, st, consistent=True)
    if violations:
        raise InvalidInputDataError("CHK-PLAN-CONSISTENT", {"violations": violations})
    violations = _violations(days, st, consistent=False)
    if violations:
        raise InvalidInputDataError("CHK-PLAN-FORMAT", {"violations": violations})
