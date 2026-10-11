"""INV-DEFERRED-POSITIVE (10.1: после стадии 13): каждый исходящий блок > 0 и кратен шагу."""
from __future__ import annotations

from typing import Sequence

from ..codes_registry.invariant_codes import INV_DEFERRED_POSITIVE
from ..types.entities import DeferredBlock
from ._fail import fail


def check_deferred(blocks: Sequence[DeferredBlock], step: int) -> None:
    for b in blocks:
        if b.minutes <= 0 or b.minutes % step:
            fail(INV_DEFERRED_POSITIVE,
                 {"source_day": b.source_day, "tariff": b.tariff, "minutes": b.minutes})
