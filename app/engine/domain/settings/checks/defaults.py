"""CHK-DEFAULTS: глобальные подстраховки CFG-MODIFIERS заданы для «Двойных переработок»,
«Оплачиваются ли переработки» и «План=Факт» (уровень 7, 3.5, 5.3)."""
from __future__ import annotations

from ..types import PEF_VALUES, Settings
from ._violations import Violation

CHK_DEFAULTS = "CHK-DEFAULTS"


def check_defaults(st: Settings) -> list[Violation]:
    gd = st.global_defaults
    out = [(CHK_DEFAULTS, {"modifier": name}) for name, value in
           (("double_overtime", gd.double_overtime), ("pays_overtime", gd.pays_overtime),
            ("plan_equals_fact", gd.plan_equals_fact)) if value is None]
    if gd.double_overtime is not None and not isinstance(gd.double_overtime, bool):
        out.append((CHK_DEFAULTS, {"modifier": "double_overtime", "value": gd.double_overtime}))
    if gd.pays_overtime is not None and not isinstance(gd.pays_overtime, bool):
        out.append((CHK_DEFAULTS, {"modifier": "pays_overtime", "value": gd.pays_overtime}))
    if gd.plan_equals_fact is not None and gd.plan_equals_fact not in PEF_VALUES:
        out.append((CHK_DEFAULTS, {"modifier": "plan_equals_fact", "value": gd.plan_equals_fact}))
    return out
