from typing import Sequence

from ..settings.types import Settings
from .codes import CodeBlock


def placement_order(blocks: Sequence[CodeBlock], st: Settings) -> tuple[CodeBlock, ...]:
    """source_day по возрастанию, затем порядок тарифов Т9."""
    order = st.placement.tariff_order
    return tuple(sorted(blocks, key=lambda b: (b.source_day, order.index(b.tariff))))
