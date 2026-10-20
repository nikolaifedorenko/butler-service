"""normalize_opening_bank(value, old_step, new_step) — нормализация остатка банка при
смене шага (4.6); возвращает значение и запись OPENING_ROUNDED (v7/R8). При равных шагах
не выполняется."""
from __future__ import annotations

from ..codes_registry.reason_codes import OPENING_KIND_BANK, OPENING_ROUNDED, STEP_OPENING
from ..types.results import Reason
from .round_signed import round_signed


def _reason(before: int, after: int, old_step: int, new_step: int) -> Reason:
    return Reason(STEP_OPENING, OPENING_ROUNDED, {
        "kind": OPENING_KIND_BANK, "before_minutes": before, "after_minutes": after,
        "delta_minutes": after - before, "old_step_minutes": old_step, "new_step_minutes": new_step})


def normalize_opening_bank(value: int, old_step: int, new_step: int) -> tuple[int, tuple[Reason, ...]]:
    if old_step == new_step:
        return value, ()
    normalized = round_signed(value, new_step)
    if normalized == value:
        return value, ()
    return normalized, (_reason(value, normalized, old_step, new_step),)
