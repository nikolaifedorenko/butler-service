from ..codes_registry.reason_codes import RESIDUAL_CARRIED
from ..types.results import Reason


def close_bank(bank_left: int, residual: int) -> tuple[int, tuple[Reason, ...]]:
    """Р18: неиспользованный положительный банк − остаток долга."""
    after = bank_left - residual
    reason = Reason("closing", RESIDUAL_CARRIED, {
        "residual_minutes": residual, "bank_before": bank_left, "bank_after": after})
    return after, ((reason,) if residual > 0 else ())
