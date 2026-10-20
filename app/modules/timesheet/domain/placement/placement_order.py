"""placement_order(blocks, st) — сортировка переносимых блоков (6.3, стадия 8, шаг 3):
source_day по возрастанию, затем порядок тарифов CFG-PLACEMENT."""
from __future__ import annotations

from typing import Sequence

from ..settings.types import Settings
from .codes import CodeBlock


def placement_order(blocks: Sequence[CodeBlock], st: Settings) -> tuple[CodeBlock, ...]:
    index = {t: i for i, t in enumerate(st.placement_order)}
    return tuple(sorted(blocks, key=lambda b: (b.source_day, index.get(b.tariff, len(index)))))
