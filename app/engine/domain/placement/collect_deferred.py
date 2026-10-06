from ..codes_registry.reason_codes import NO_RECEIVER
from ..settings.types import Settings
from ..types.entities import DeferredBlock
from ..types.results import Reason
from .codes import Codes
from .merge_same_blocks import merge_same_blocks
from .pending_blocks import pending_blocks
from .placement_order import placement_order


def collect_deferred(codes: Codes, st: Settings) -> tuple[tuple[DeferredBlock, ...], tuple[Reason, ...]]:
    """Неразмещённые остатки → deferred_blocks + NO_RECEIVER."""
    blocks = placement_order(merge_same_blocks(pending_blocks(codes)), st)
    out = tuple(DeferredBlock(b.source_day, b.tariff, b.minutes, NO_RECEIVER) for b in blocks)
    return out, tuple(Reason("deferred", NO_RECEIVER, {
        "source_day": b.source_day, "tariff": b.tariff, "minutes": b.minutes}) for b in out)
