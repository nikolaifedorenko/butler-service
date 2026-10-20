"""CHK-CODES-EXIST: для каждой категории и каждого представимого веса (1 и 2) код
`<категория>[<вес>]` присутствует в CFG-WEIGHTS (3.5); вес 1 — без суффикса, иначе
десятичная запись веса слитно («ДЯ2»)."""
from __future__ import annotations

from ..types import Settings
from ._violations import Violation

CHK_CODES_EXIST = "CHK-CODES-EXIST"
REPRESENTABLE_WEIGHTS = (1, 2)


def code_of(category_code: str, weight: int) -> str:
    """Общее правило имени кода (CFG-WEIGHTS): суффикс веса пишется слитно."""
    return category_code + ("" if weight == 1 else str(weight))


def check_codes_exist(st: Settings) -> list[Violation]:
    return [(CHK_CODES_EXIST, {"category": c.code, "weight": w, "expected_code": code_of(c.code, w)})
            for c in st.categories for w in REPRESENTABLE_WEIGHTS
            if code_of(c.code, w) not in st.weights]
