"""normalize_deferred(blocks, old_step, new_step) — физические минуты каждого входящего
блока отдельно (округление суммы запрещено); source_day и tariff сохраняются; блок,
округлённый до нуля, исключается, запись остаётся (4.6, v7/R8). Вход подаётся уже
канонически отсортированным (3.3, v7/R4 — сортирует домен до стадии 2); порядок записей
OPENING_ROUNDED следует порядку входа."""
from __future__ import annotations

from typing import Sequence

from ..codes_registry.reason_codes import OPENING_KIND_DEFERRED_BLOCK, OPENING_ROUNDED, STEP_OPENING
from ..types.entities import DeferredBlock
from ..types.results import Reason
from .round_signed import round_signed


def _reason(block: DeferredBlock, after: int, old_step: int, new_step: int) -> Reason:
    return Reason(STEP_OPENING, OPENING_ROUNDED, {
        "kind": OPENING_KIND_DEFERRED_BLOCK, "before_minutes": block.minutes, "after_minutes": after,
        "delta_minutes": after - block.minutes, "old_step_minutes": old_step,
        "new_step_minutes": new_step, "source_day": block.source_day, "tariff": block.tariff})


def normalize_deferred(blocks: Sequence[DeferredBlock], old_step: int,
                       new_step: int) -> tuple[tuple[DeferredBlock, ...], tuple[Reason, ...]]:
    if old_step == new_step:
        return tuple(blocks), ()
    out, reasons = [], []
    for block in blocks:
        normalized = round_signed(block.minutes, new_step)
        if normalized != block.minutes:
            reasons.append(_reason(block, normalized, old_step, new_step))
        if normalized > 0:
            out.append(DeferredBlock(block.source_day, block.tariff, normalized))
    return tuple(out), tuple(reasons)
