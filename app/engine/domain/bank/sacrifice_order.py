import datetime as dt

from ..placement.codes import CodeBlock, Codes
from ..settings.types import Settings


def sacrifice_order(codes: Codes, st: Settings) -> tuple[CodeBlock, ...]:
    """Т6 → source_day → placed_day (размещённые по дате, неразмещённые последними)."""
    order = st.cascade_order
    late = dt.date.max
    return tuple(sorted(codes.blocks(), key=lambda b: (order.index(b.tariff), b.source_day,
                                                       b.placed_day or late)))
