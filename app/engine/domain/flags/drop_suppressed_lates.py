"""drop_suppressed_lates(lates, plan_equals_fact_applied) — единственное подавление (v7):
в день с применённым «План=Факт» не ставится LATE(None) — сотрудник официально не
ожидался (6.6, RUL-LATE-NONE-PERSISTS)."""
from __future__ import annotations

from typing import Sequence

from ..types.results import Flag


def drop_suppressed_lates(lates: Sequence[Flag], plan_equals_fact_applied: bool) -> tuple[Flag, ...]:
    if not plan_equals_fact_applied:
        return tuple(lates)
    return tuple(f for f in lates if f.data.get("actual_at") is not None)
