"""resolve_plan_equals_fact(day, st) — разрешение модификатора «План=Факт» (CFG-MODIFIERS):
«Авто» разрешается в «Да» только колонкой CFG-DAY-CODES и только для значений с часами
(единственный источник «Авто» — v7/R19). Возвращает (разрешено в «Да», policy для трассы):
policy = "yes" при явной записи «Да» (уровни 1–6 либо глобальный дефолт), "auto_code" —
когда разрешение шло через «Авто» → колонку (6.2)."""
from __future__ import annotations

from ..codes_registry.reason_codes import POLICY_AUTO_CODE, POLICY_YES
from ..settings.resolve_modifier import resolve_modifier
from ..settings.types import MOD_PLAN_EQUALS_FACT, PEF_AUTO, PEF_YES, Settings
from ..types.entities import Day
from .policy_of import policy_of


def resolve_plan_equals_fact(day: Day, st: Settings) -> tuple[bool, str | None]:
    resolved = resolve_modifier(MOD_PLAN_EQUALS_FACT, day, st)
    if resolved == PEF_YES:
        return True, POLICY_YES
    if resolved == PEF_AUTO:
        policy = policy_of(day, st)
        auto_yes = policy.carries_hours and policy.plan_equals_fact_auto
        return auto_yes, POLICY_AUTO_CODE if auto_yes else None
    return False, None
