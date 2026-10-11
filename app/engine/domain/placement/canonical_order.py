"""Канонический порядок блоков (3.3, v7/R2–R4): source_day ↑, затем порядок тарифов
CFG-PLACEMENT, затем minutes ↑ — относительный порядок не зависит от порядка строк
адаптера (RUL-DETERMINISM-AND-ORDER)."""
from __future__ import annotations

from typing import Sequence

from ..settings.types import Settings
from ..types.entities import DeferredBlock


def deferred_sort_key(st: Settings):
    order = {tariff: i for i, tariff in enumerate(st.placement_order)}
    return lambda b: (b.source_day, order.get(b.tariff, len(order)), b.minutes)


def sort_deferred(blocks: Sequence[DeferredBlock], st: Settings) -> tuple[DeferredBlock, ...]:
    return tuple(sorted(blocks, key=deferred_sort_key(st)))
