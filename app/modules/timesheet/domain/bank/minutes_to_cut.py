"""minutes_to_cut(rest, weight, available, step) — физические минуты изъятия
(CFG-GRANULE, неделимая гранула): число гранул = min(available // q, rest // (q × weight));
снято = гранулы × q. Гранула дороже остатка → изъятие 0 (EX-21)."""
from __future__ import annotations

from .granules_that_fit import granules_that_fit


def minutes_to_cut(rest: int, weight: int, available: int, step: int) -> int:
    granules = min(available // step, granules_that_fit(rest, weight, step))
    return granules * step
