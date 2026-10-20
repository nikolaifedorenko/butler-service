"""accept_deferred(deferred_in, codes) — входящие блоки с placed_day = None (6.3, стадия 6);
в банк повторно не зачисляются (RUL-DEFERRED-IN-ACCEPTED). Вход предварительно
канонически сортируется (v7/R4)."""
from __future__ import annotations

from typing import Sequence

from ..settings.types import Settings
from ..types.entities import DeferredBlock
from .canonical_order import sort_deferred
from .codes import Codes


def accept_deferred(deferred_in: Sequence[DeferredBlock], codes: Codes, st: Settings) -> Codes:
    for block in sort_deferred(deferred_in, st):
        codes.add(block.source_day, block.tariff, block.minutes, None)
    return codes
