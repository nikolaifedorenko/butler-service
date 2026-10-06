from typing import Sequence

from ..types.entities import DeferredBlock
from .codes import Codes


def accept_deferred(deferred_in: Sequence[DeferredBlock], codes: Codes) -> Codes:
    """Р30: входящие блоки — с placed_day = None, source_day и тариф сохранены."""
    for b in deferred_in:
        codes.add(b.source_day, b.tariff, b.minutes, None)
    return codes
