"""CHK-PLACEMENT-FULL: порядок тарифов CFG-PLACEMENT содержит все коды CFG-WEIGHTS,
без повторов (5.3)."""
from __future__ import annotations

from ..types import Settings
from ._violations import Violation

CHK_PLACEMENT_FULL = "CHK-PLACEMENT-FULL"


def check_placement_full(st: Settings) -> list[Violation]:
    order = st.placement_order
    problems = {"duplicates": tuple(t for t in set(order) if order.count(t) > 1),
                "missing": tuple(sorted(set(st.weights) - set(order))),
                "unknown": tuple(t for t in order if t not in st.weights)}
    return [] if not any(problems.values()) else [(CHK_PLACEMENT_FULL, problems)]
