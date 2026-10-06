from dataclasses import replace
from typing import Sequence

from ..codes_registry.reason_codes import OPENING_ROUNDED
from ..types.entities import DeferredBlock
from ..types.results import Reason
from .round_signed import round_signed


def normalize_deferred(blocks: Sequence[DeferredBlock], old_step: int,
                       new_step: int) -> tuple[tuple[DeferredBlock, ...], tuple[Reason, ...]]:
    """Каждый блок отдельно; округлённые до нуля исключаются."""
    if old_step == new_step:
        return tuple(blocks), ()
    pairs = [(b, round_signed(b.minutes, new_step)) for b in blocks]
    reasons = tuple(Reason("opening", OPENING_ROUNDED, {
        "kind": "deferred", "before_minutes": b.minutes, "after_minutes": a, "delta_minutes": a - b.minutes,
        "old_step_minutes": old_step, "new_step_minutes": new_step, "source_day": b.source_day,
        "tariff": b.tariff}) for b, a in pairs if a != b.minutes)
    return tuple(replace(b, minutes=a) for b, a in pairs if a > 0), reasons
