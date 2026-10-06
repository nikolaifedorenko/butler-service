from ..settings.resolve_modifier import resolve_modifier
from ..settings.types import AUTO, MOD_PLAN_EQUALS_FACT, Settings
from ..types.entities import Day
from .policy_of import policy_of


def resolve_plan_equals_fact(day: Day, st: Settings) -> bool:
    """Да/Нет/Авто → bool; Авто = Да, если значение несёт часы и Т1 или Т-Группы говорят «Да»."""
    value = resolve_modifier(MOD_PLAN_EQUALS_FACT, day.employee_id, day.group, day.day, st, AUTO)
    if value != AUTO:
        return bool(value)
    policy = policy_of(day, st)
    group = st.groups.get(day.group)
    by_group = bool(group and group.plan_equals_fact_auto)
    return policy.carries_hours and (policy.plan_equals_fact_auto or by_group)
