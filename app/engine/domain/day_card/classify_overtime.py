from typing import Sequence

from ..settings.types import Settings
from ..types.entities import Interval
from .split_by_category import split_by_category


def classify_overtime(parts: Sequence[Interval], st: Settings) -> dict[str, int]:
    """Суммы переработки по категориям (без округления, Р10)."""
    out: dict[str, int] = {}
    for name, minutes in ((n, m) for p in parts for n, m in split_by_category(p, st).items()):
        out[name] = out.get(name, 0) + minutes
    return out
