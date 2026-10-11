"""CHK-MODIFIER-TYPE: тип значения ModifierEntry соответствует модификатору —
булево для double_overtime/pays_overtime/counts_in_ut; "yes"/"no"/"auto" для
plan_equals_fact (3.5, 5.3)."""
from __future__ import annotations

from ..types import MOD_COUNTS_IN_UT, MOD_DOUBLE, MOD_PAYS, MOD_PLAN_EQUALS_FACT, PEF_VALUES, Settings
from ._violations import Violation

CHK_MODIFIER_TYPE = "CHK-MODIFIER-TYPE"
BOOL_MODIFIERS = (MOD_DOUBLE, MOD_PAYS, MOD_COUNTS_IN_UT)


def _type_ok(entry) -> bool:
    if entry.name in BOOL_MODIFIERS:
        return isinstance(entry.value, bool)
    if entry.name == MOD_PLAN_EQUALS_FACT:
        return entry.value in PEF_VALUES
    return False


def check_modifier_type(st: Settings) -> list[Violation]:
    return [(CHK_MODIFIER_TYPE, {"name": e.name, "value": e.value})
            for e in st.modifiers if not _type_ok(e)]
