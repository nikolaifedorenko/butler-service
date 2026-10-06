from dataclasses import dataclass

from ..codes_registry.reason_codes import CODE_CUT
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


def sacrifice_codes(need: int, codes: Codes, st: Settings) -> Sacrificed:
    """Стадия 11: обход блоков по sacrifice_order и изъятие целых гранул."""
    rest, cuts = need, []
    for b in sacrifice_order(codes, st):
        weight = st.weights[b.tariff]
        taken = minutes_to_cut(rest, weight, codes.get(b.source_day, b.tariff, b.placed_day), st.step_minutes)
        if taken > 0:
            codes.take(b.source_day, b.tariff, b.placed_day, taken)
            cuts.append(Cut(b.source_day, b.placed_day, b.tariff, taken, debt_paid_by_cut(taken, weight)))
            rest -= cuts[-1].paid_minutes
    reasons = tuple(Reason("cascade", CODE_CUT, {
        "source_day": c.source_day, "placed_day": c.placed_day, "tariff": c.tariff,
        "taken_minutes": c.taken_minutes, "paid_minutes": c.paid_minutes}) for c in cuts)
    return Sacrificed(tuple(cuts), reasons, rest)
