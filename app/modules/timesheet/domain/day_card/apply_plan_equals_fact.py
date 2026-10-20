"""apply_plan_equals_fact(day, fact, plan, has_event, st) → (plan_minutes, applied).

Единый предикат применения (CFG-MODIFIERS — единственный источник условия, v7/R30):
carries_hours ∧ модификатор «Да» ∧ has_presence_event = False ∧ полный факт = 0.
При applied план := 0; синтетические отметки, факт и рабочее время НЕ создаются
(R12/R16); день освобождается от недостачи (R15). Окно, план строки Табеля, График
и согласованные отсутствия в предикате не участвуют (12.23)."""
from __future__ import annotations

from ..settings.types import Settings
from ..types.entities import Day, Minutes
from .policy_of import policy_of
from .resolve_plan_equals_fact import resolve_plan_equals_fact


def apply_plan_equals_fact(day: Day, fact: Minutes, plan: Minutes, has_event: bool,
                           st: Settings) -> tuple[Minutes, bool]:
    resolved_yes, _ = resolve_plan_equals_fact(day, st)
    applied = (policy_of(day, st).carries_hours and resolved_yes and not has_event and fact == 0)
    return (0, True) if applied else (plan, False)
