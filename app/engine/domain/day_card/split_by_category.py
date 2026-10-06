from ..settings.types import Settings
from ..types.entities import Interval
from .category_cuts import category_cuts
from .category_of import category_of


def split_by_category(interval: Interval, st: Settings) -> dict[str, int]:
    """Минуты интервала по категориям Т3."""
    cuts = category_cuts(interval, st)
    out: dict[str, int] = {}
    for a, b in zip(cuts, cuts[1:]):
        name = category_of(a, st).name
        out[name] = out.get(name, 0) + (b - a)
    return out
