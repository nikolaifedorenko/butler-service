from dataclasses import dataclass
from typing import Sequence

from ..codes_registry.reason_codes import UNPAID_CREDITED
from ..settings.types import Settings
from ..types.results import DayCard, Reason
from .codes import Codes


@dataclass(frozen=True)
class Credited:
    credited_minutes: int        # взвешенные минуты банка
    taken_minutes: int           # снятые физические минуты (И17)
    reasons: tuple[Reason, ...]


def credit_unpaid(cards: Sequence[DayCard], codes: Codes, st: Settings) -> Credited:
    """Р13: собственные коды дней с pays_overtime = Нет → в банк по весу. Входящие не трогает."""
    rows = [(c.day, t, m) for c in cards if not c.pays_overtime for t, m in c.codes.items()]
    for day, tariff, minutes in rows:
        codes.take(day, tariff, None, minutes)
    reasons = tuple(Reason("credit_unpaid", UNPAID_CREDITED, {
        "day": d, "tariff": t, "taken_minutes": m, "credited_minutes": m * st.weights[t]}) for d, t, m in rows)
    return Credited(sum(m * st.weights[t] for _, t, m in rows), sum(m for _, _, m in rows), reasons)
