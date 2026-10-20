"""granules_that_fit(rest, weight, step) — сколько гранул покрывает остаток долга
(CFG-GRANULE): rest // (q × weight)."""
from __future__ import annotations


def granules_that_fit(rest: int, weight: int, step: int) -> int:
    return rest // (step * weight)
