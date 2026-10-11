"""close_bank(bank_left, residual) — закрывающий банк = неиспользованный положительный
− остаток долга (RUL-CLOSING-BANK); банк может быть отрицательным — штатный перенос долга.
RESIDUAL_CARRIED при residual > 0."""
from __future__ import annotations

from ..codes_registry.reason_codes import RESIDUAL_CARRIED, STEP_CLOSING
from ..types.results import Reason


def close_bank(bank_left: int, residual: int) -> tuple[int, tuple[Reason, ...]]:
    closed = bank_left - residual
    if residual <= 0:
        return closed, ()
    return closed, (Reason(STEP_CLOSING, RESIDUAL_CARRIED, {
        "residual_minutes": residual, "bank_before": bank_left, "bank_after": closed}),)
