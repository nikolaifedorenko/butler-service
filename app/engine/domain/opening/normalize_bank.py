from ..codes_registry.reason_codes import OPENING_ROUNDED
from ..types.results import Reason
from .round_signed import round_signed


def normalize_opening_bank(value: int, old_step: int, new_step: int) -> tuple[int, tuple[Reason, ...]]:
    """Знаковый остаток банка к новому шагу; при неизменном шаге не выполняется."""
    if old_step == new_step:
        return value, ()
    after = round_signed(value, new_step)
    data = {"kind": "bank", "before_minutes": value, "after_minutes": after, "delta_minutes": after - value,
            "old_step_minutes": old_step, "new_step_minutes": new_step}
    return after, ((Reason("opening", OPENING_ROUNDED, data),) if after != value else ())
