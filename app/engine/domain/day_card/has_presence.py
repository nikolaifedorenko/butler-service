from typing import Sequence

from ..types.entities import CalcMark


def has_presence(day_marks: Sequence[CalcMark], open_at_start: bool) -> bool:
    """Фактическое присутствие: реальные расчётные отметки дня или открытое состояние в 00:00."""
    return bool(day_marks) or open_at_start
