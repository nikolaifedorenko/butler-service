"""credit_unpaid(cards, codes, st) — дни с pays_overtime = Нет: снять собственные коды
и зачислить в банк по весу (6.3, стадия 7; RUL-UNPAID-TO-BANK). Входящие блоки не трогает
(их source_day вне периода — CHK-DEFERRED-IN). Записи UNPAID_CREDITED: дни по возрастанию,
внутри дня — порядок тарифов CFG-PLACEMENT (v7/R3)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..codes_registry.reason_codes import STEP_CREDIT_UNPAID, UNPAID_CREDITED
from ..settings.types import Settings
from ..types.results import DayCard, Reason
from .codes import Codes


@dataclass(frozen=True)
class Credited:
    credited_minutes: int          # взвешенные минуты банка
    taken_minutes: int             # снятые физические минуты (INV-MINUTES-CONSERVED)
    reasons: tuple[Reason, ...]


def _rows(cards: Sequence[DayCard], st: Settings) -> list[tuple]:
    index = {t: i for i, t in enumerate(st.placement_order)}
    rows = [(c.day, t, m) for c in cards if not c.pays_overtime for t, m in c.codes.items()]
    return sorted(rows, key=lambda r: (r[0], index.get(r[1], len(index))))


def credit_unpaid(cards, codes: Codes, st: Settings) -> Credited:
    rows = _rows(cards, st)
    for day, tariff, minutes in rows:
        codes.take(day, tariff, None, minutes)
    reasons = tuple(Reason(STEP_CREDIT_UNPAID, UNPAID_CREDITED, {
        "day": d, "tariff": t, "taken_minutes": m, "credited_minutes": m * st.weights[t]})
        for d, t, m in rows)
    return Credited(sum(m * st.weights[t] for _, t, m in rows), sum(m for _, _, m in rows), reasons)
