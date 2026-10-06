from typing import Sequence

from ..types.entities import CalcMark


def sort_marks(marks: Sequence[CalcMark]) -> tuple[CalcMark, ...]:
    """Стабильная сортировка по моменту: при равенстве сохраняется порядок источника."""
    return tuple(sorted(marks, key=lambda m: m.at_calc))
