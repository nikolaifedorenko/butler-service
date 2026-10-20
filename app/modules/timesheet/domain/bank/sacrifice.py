"""sacrifice_codes(need, codes, st) — композиция каскада (6.3, стадия 11): обход блоков
по sacrifice_order, изъятие целых гранул; Codes.take — только при положительном изъятии
и для конкретного блока (6.5 п.3). На каждый блок — Cut + CODE_CUT."""
from __future__ import annotations

from dataclasses import dataclass

from ..codes_registry.reason_codes import CODE_CUT, STEP_CASCADE
from ..placement.codes import Codes
from ..settings.types import Settings
from ..types.results import Cut, Reason
from .debt_paid import debt_paid_by_cut
from .minutes_to_cut import minutes_to_cut
from .sacrifice_order import sacrifice_order


@dataclass(frozen=True)
class Sacrificed:
    cuts: tuple[Cut, ...]
    reasons: tuple[Reason, ...]
    residual: int


def _cut_one(rest: int, block, codes: Codes, st: Settings) -> Cut | None:
    weight = st.weights[block.tariff]
    available = codes.get(block.source_day, block.tariff, block.placed_day)
    taken = minutes_to_cut(rest, weight, available, st.step_minutes)
    if taken <= 0:
        return None
    codes.take(block.source_day, block.tariff, block.placed_day, taken)
    return Cut(block.source_day, block.placed_day, block.tariff, taken,
               debt_paid_by_cut(taken, weight))


def sacrifice_codes(need: int, codes: Codes, st: Settings) -> Sacrificed:
    rest, cuts = need, []
    for block in sacrifice_order(codes, st):
        cut = _cut_one(rest, block, codes, st)
        if cut is not None:
            cuts.append(cut)
            rest -= cut.paid_minutes
    reasons = tuple(Reason(STEP_CASCADE, CODE_CUT, {
        "source_day": c.source_day, "placed_day": c.placed_day, "tariff": c.tariff,
        "taken_minutes": c.taken_minutes, "paid_minutes": c.paid_minutes}) for c in cuts)
    return Sacrificed(tuple(cuts), reasons, rest)
