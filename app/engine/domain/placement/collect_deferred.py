"""collect_deferred(codes, st) — окончательные (в view — предварительные) неразмещённые
остатки + NO_RECEIVER в exceptions (6.3, стадия 13). Порядок deferred_blocks:
source_day ↑, затем порядок тарифов CFG-PLACEMENT (3.4, v7/R2)."""
from __future__ import annotations

from ..codes_registry.reason_codes import NO_RECEIVER, STEP_DEFERRED
from ..settings.types import Settings
from ..types.entities import DeferredBlock
from ..types.results import Reason
from .codes import Codes
from .merge_same_blocks import merge_same_blocks
from .pending_blocks import pending_blocks
from .placement_order import placement_order


def collect_deferred(codes: Codes, st: Settings) -> tuple[tuple[DeferredBlock, ...], tuple[Reason, ...]]:
    blocks = placement_order(merge_same_blocks(pending_blocks(codes)), st)
    out = tuple(DeferredBlock(b.source_day, b.tariff, b.minutes) for b in blocks)
    reasons = tuple(Reason(STEP_DEFERRED, NO_RECEIVER, {
        "source_day": b.source_day, "tariff": b.tariff, "minutes": b.minutes}) for b in out)
    return out, reasons
